import os
import importlib
import logging
from optparse import make_option

from django.core.management.base import BaseCommand

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


class Command(BaseCommand):
    """
    Runs RQ workers on specified queues. Note that all queues passed into a
    single rqworker command must share the same connection.

    Example usage:
    python manage.py rqworker high medium low
    """
    option_list = BaseCommand.option_list + (
        make_option(
            '--burst',
            action='store_true',
            dest='burst',
            default=False,
            help='Run worker in burst mode'
        ),
        make_option(
            '--worker-class',
            action='store',
            dest='worker_class',
            default='rq.Worker',
            help='RQ Worker class to use'
        ),
        make_option(
            '--name',
            action='store',
            dest='name',
            default=None,
            help='Name of the worker'
        ),
        make_option(
            '--worker-ttl',
            action='store',
            type="int",
            dest='worker_ttl',
            default=420,
            help='Default worker timeout to be used'
        ),
        make_option(
            '--pid',
            action='store',
            dest='pid',
            default=None,
            help='PID file to write the worker`s pid into'
        ),
    )
    args = '<queue queue ...>'

    def handle(self, *args, **options):

        pid = options.get('pid')
        if pid:
            with open(os.path.expanduser(pid), "w") as fp:
                fp.write(str(os.getpid()))

        try:
            # Instantiate a worker
            worker_class = import_attribute(options.get('worker_class', 'rq.Worker'))
            queues = get_queues(*args)
            w = worker_class(
                queues,
                connection=queues[0].connection,
                name=options['name'],
                exception_handlers=get_exception_handlers() or None,
                default_worker_ttl=options['worker_ttl']
            )

            # Call use_connection to push the redis connection into LocalStack
            # without this, jobs using RQ's get_current_job() will fail
            use_connection(w.connection)
            w.work(burst=options.get('burst', False))
        except ConnectionError as e:
            print(e)
