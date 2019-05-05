import os
import sys
from distutils.version import LooseVersion

from redis.exceptions import ConnectionError
from rq import use_connection
from rq.logutils import setup_loghandlers

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from django.utils.version import get_version
from django_rq.workers import get_worker


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
                            help='RQ Worker class to use')
        parser.add_argument('--pid', action='store', dest='pid',
                            default=None, help='PID file to write the worker`s pid into')
        parser.add_argument('--burst', action='store_true', dest='burst',
                            default=False, help='Run worker in burst mode')
        parser.add_argument('--name', action='store', dest='name',
                            default=None, help='Name of the worker')
        parser.add_argument('--queue-class', action='store', dest='queue_class',
                            help='Queues class to use')
        parser.add_argument('--job-class', action='store', dest='job_class',
                            help='Jobs class to use')
        parser.add_argument('--worker-ttl', action='store', type=int,
                            dest='worker_ttl', default=420,
                            help='Default worker timeout to be used')
        parser.add_argument('--sentry-dsn', action='store', default=None, dest='sentry-dsn',
                            help='Report exceptions to this Sentry DSN')

        if LooseVersion(get_version()) >= LooseVersion('1.10'):
            parser.add_argument('args', nargs='*', type=str,
                                help='The queues to work on, separated by space')

    def handle(self, *args, **options):
        pid = options.get('pid')
        if pid:
            with open(os.path.expanduser(pid), "w") as fp:
                fp.write(str(os.getpid()))
        sentry_dsn = options.get('sentry-dsn')
        if sentry_dsn is None:
            sentry_dsn = getattr(settings, 'SENTRY_DSN', None)

        # Verbosity is defined by default in BaseCommand for all commands
        verbosity = options.get('verbosity')
        if verbosity >= 2:
            level = 'DEBUG'
        elif verbosity == 0:
            level = 'WARNING'
        else:
            level = 'INFO'
        setup_loghandlers(level)

        try:
            # Instantiate a worker
            worker_kwargs = {
                'worker_class': options['worker_class'],
                'queue_class': options['queue_class'],
                'job_class': options['job_class'],
                'name': options['name'],
                'default_worker_ttl': options['worker_ttl'],
            }
            w = get_worker(*args, **worker_kwargs)

            # Call use_connection to push the redis connection into LocalStack
            # without this, jobs using RQ's get_current_job() will fail
            use_connection(w.connection)
            # Close any opened DB connection before any fork
            reset_db_connections()

            if sentry_dsn:
                try:
                    from rq.contrib.sentry import register_sentry
                    register_sentry(sentry_dsn)
                except ImportError:
                    self.stdout.write(self.style.ERROR("Please install sentry-sdk using `pip install sentry-sdk`"))
                    sys.exit(1)

            w.work(burst=options.get('burst', False))
        except ConnectionError as e:
            print(e)
            sys.exit(1)
