import os
import sys

from rq.serializers import resolve_serializer
from rq.worker_pool import WorkerPool
from rq.logutils import setup_loghandlers

from django.core.management.base import BaseCommand

from ...jobs import get_job_class
from ...utils import configure_sentry
from ...queues import get_queues
from ...workers import get_worker_class


class Command(BaseCommand):
    """
    Runs RQ pool with x number of workers on specified queues.
    Note that all queues passed into a
    single rqworker-pool command must share the same connection.

    Example usage:
    python manage.py rqworker-pool high medium low --num-workers 4
    """

    args = '<queue queue ...>'

    def add_arguments(self, parser):
        parser.add_argument('--num-workers', action='store', dest='num_workers',
                            type=int, default=1, help='Number of workers to spawn')
        parser.add_argument('--worker-class', action='store', dest='worker_class',
                            help='RQ Worker class to use')
        parser.add_argument('--pid', action='store', dest='pid',
                            default=None, help='PID file to write the worker`s pid into')
        parser.add_argument('--burst', action='store_true', dest='burst',
                            default=False, help='Run worker in burst mode')
        parser.add_argument('--queue-class', action='store', dest='queue_class',
                            help='Queues class to use')
        parser.add_argument('--job-class', action='store', dest='job_class',
                            help='Jobs class to use')
        parser.add_argument('--serializer', action='store', default='rq.serializers.DefaultSerializer', dest='serializer',
                            help='Specify a custom Serializer.')
        parser.add_argument('args', nargs='*', type=str,
                            help='The queues to work on, separated by space')

        # Args present in `rqworker` command but not yet implemented here
        # parser.add_argument('--worker-ttl', action='store', type=int,
        #                     dest='worker_ttl', default=420,
        #                     help='Default worker timeout to be used')
        # parser.add_argument('--max-jobs', action='store', default=None, dest='max_jobs', type=int,
        #                     help='Maximum number of jobs to execute')
        # parser.add_argument('--with-scheduler', action='store_true', dest='with_scheduler',
        #                     default=False, help='Run worker with scheduler enabled')

        # Sentry arguments
        parser.add_argument('--sentry-dsn', action='store', default=None, dest='sentry_dsn',
                            help='Report exceptions to this Sentry DSN')
        parser.add_argument('--sentry-ca-certs', action='store', default=None, dest='sentry_ca_certs',
                            help='A path to an alternative CA bundle file in PEM-format')
        parser.add_argument('--sentry-debug', action='store', default=False, dest='sentry_debug',
                            help='Turns debug mode on or off.')

    def handle(self, *args, **options):
        pid = options.get('pid')
        if pid:
            with open(os.path.expanduser(pid), "w") as fp:
                fp.write(str(os.getpid()))

        # Verbosity is defined by default in BaseCommand for all commands
        verbosity = options.get('verbosity')
        if verbosity >= 2:
            logging_level = 'DEBUG'
        elif verbosity == 0:
            logging_level = 'WARNING'
        else:
            logging_level = 'INFO'
        setup_loghandlers(logging_level)

        sentry_dsn = options.pop('sentry_dsn')
        if sentry_dsn:
            try:
                configure_sentry(sentry_dsn, **options)
            except ImportError:
                self.stderr.write("Please install sentry-sdk using `pip install sentry-sdk`")
                sys.exit(1)

        job_class = get_job_class(options['job_class'])
        queues = get_queues(*args, **{'job_class': job_class, 'queue_class': options['queue_class']})
        worker_class = get_worker_class(options.get('worker_class', None))
        serializer = resolve_serializer(options['serializer'])

        pool = WorkerPool(
            queues=queues,
            connection=queues[0].connection,
            num_workers=options['num_workers'],
            serializer=serializer,
            worker_class=worker_class,
            job_class=job_class,
        )
        pool.start(burst=options.get('burst', False), logging_level=logging_level)
