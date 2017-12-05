from distutils.version import LooseVersion
import os
import importlib
import logging
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from django.utils import autoreload
from django.utils.version import get_version

from django_rq.queues import get_queues
from django_rq.workers import get_exception_handlers

from redis.exceptions import ConnectionError
from rq import use_connection
from rq.utils import ColorizingStreamHandler

# Setup logging for RQWorker if not already configured
logger = logging.getLogger('rq.worker')
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt='%(asctime)s %(message)s',
                                  datefmt='%H:%M:%S')
    handler = ColorizingStreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# Copied from rq.utils
def import_attribute(name):
    """Return an attribute from a dotted path name (e.g. "path.to.func")."""
    module_name, attribute = name.rsplit('.', 1)
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


def reset_db_connections():
    for c in connections.all():
        c.close()


class Command(BaseCommand):
    """
    Runs RQ workers on specified queues. Note that all queues passed into a
    single rqworker command must share the same connection.

    Example usage:
    python manage.py rqworker high medium low
    """

    args = '<queue queue ...>'

    def add_arguments(self, parser):
        parser.add_argument('--worker-class', action='store', dest='worker_class',
                            default='rq.Worker', help='RQ Worker class to use')
        parser.add_argument('--pid', action='store', dest='pid',
                            default=None, help='PID file to write the worker`s pid into')
        parser.add_argument('--burst', action='store_true', dest='burst',
                            default=False, help='Run worker in burst mode')
        parser.add_argument('--name', action='store', dest='name',
                            default=None, help='Name of the worker')
        parser.add_argument('--queue-class', action='store', dest='queue_class',
                            default='django_rq.queues.DjangoRQ', help='Queues class to use')
        parser.add_argument('--worker-ttl', action='store', type=int,
                            dest='worker_ttl', default=420,
                            help='Default worker timeout to be used')
        parser.add_argument('--sentry-dsn', action='store', default=None, dest='sentry-dsn',
                            help='Report exceptions to this Sentry DSN')
        parser.add_argument('--autoreload', action='store_true', dest='use_reloader',
                            help='Auto-reloads the worker code.')

        if LooseVersion(get_version()) >= LooseVersion('1.10'):
            parser.add_argument('args', nargs='*', type=str,
                                help='The queues to work on, separated by space')

    def handle(self, *args, **options):
        if options['use_reloader']:
            if not settings.DEBUG:
                logger.warning('You are using --autoreload in production.')
            autoreload.main(self.inner_handle, args, options)
        else:
            self.inner_handle(args, **options)

    def inner_handle(self, *args, **options):
        # If an exception was silenced in ManagementUtility.execute in order
        # to be raised in the child process, raise it now.
        autoreload.raise_last_exception()

        pid = options.get('pid')
        if pid:
            with open(os.path.expanduser(pid), "w") as fp:
                fp.write(str(os.getpid()))
        sentry_dsn = options.get('sentry-dsn')
        try:
            # Instantiate a worker
            worker_class = import_attribute(options['worker_class'])
            queues = get_queues(*args, queue_class=import_attribute(options['queue_class']))
            w = worker_class(
                queues,
                connection=queues[0].connection,
                name=options['name'],
                exception_handlers=get_exception_handlers() or None,
                default_worker_ttl=options['worker_ttl']
            )
            if options['use_reloader']:
                w._install_signal_handlers = lambda s: None
                w.register_death()

            # Call use_connection to push the redis connection into LocalStack
            # without this, jobs using RQ's get_current_job() will fail
            use_connection(w.connection)
            # Close any opened DB connection before any fork
            reset_db_connections()

            if sentry_dsn:
                try:
                    from raven import Client
                    from raven.transport.http import HTTPTransport
                    from rq.contrib.sentry import register_sentry
                    client = Client(sentry_dsn, transport=HTTPTransport)
                    register_sentry(client, w)
                except ImportError:
                    self.stdout.write(self.style.ERROR("Please install sentry. For example `pip install raven`"))
                    sys.exit(1)

            logger.info('Starting rq worker')
            w.work(burst=options.get('burst', False))
        except ConnectionError as e:
            print(e)
            sys.exit(1)
