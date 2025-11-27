import os
import sys

from django.core.management.base import BaseCommand
from redis.exceptions import ConnectionError
from rq.logutils import setup_loghandlers

from ...utils import reset_db_connections
from ...workers import get_worker


class Command(BaseCommand):
    """
    Runs RQ workers on specified queues. Note that all queues passed into a
    single rqworker command must share the same connection.

    Example usage:
    python manage.py rqworker high medium low
    """

    args = '<queue queue ...>'

    def add_arguments(self, parser):
        parser.add_argument('--worker-class', action='store', dest='worker_class', help='RQ Worker class to use')
        parser.add_argument(
            '--pid', action='store', dest='pid', default=None, help='PID file to write the worker`s pid into'
        )
        parser.add_argument(
            '--burst', action='store_true', dest='burst', default=False, help='Run worker in burst mode'
        )
        parser.add_argument(
            '--with-scheduler',
            action='store_true',
            dest='with_scheduler',
            default=False,
            help='Run worker with scheduler enabled',
        )
        parser.add_argument('--name', action='store', dest='name', default=None, help='Name of the worker')
        parser.add_argument('--queue-class', action='store', dest='queue_class', help='Queues class to use')
        parser.add_argument('--job-class', action='store', dest='job_class', help='Jobs class to use')
        parser.add_argument(
            '--worker-ttl',
            action='store',
            type=int,
            dest='worker_ttl',
            default=420,
            help='Default worker timeout to be used',
        )
        parser.add_argument(
            '--max-jobs',
            action='store',
            default=None,
            dest='max_jobs',
            type=int,
            help='Maximum number of jobs to execute',
        )
        parser.add_argument(
            '--max-idle-time',
            action='store',
            default=None,
            dest='max_idle_time',
            type=int,
            help='Seconds to wait for job before shutting down',
        )
        parser.add_argument(
            '--serializer',
            action='store',
            default='rq.serializers.DefaultSerializer',
            dest='serializer',
            help='Specify a custom Serializer.',
        )
        parser.add_argument('args', nargs='*', type=str, help='The queues to work on, separated by space')

    def handle(self, *args, **options):
        pid = options.get('pid')
        if pid:
            with open(os.path.expanduser(pid), "w") as fp:
                fp.write(str(os.getpid()))

        # Verbosity is defined by default in BaseCommand for all commands
        verbosity = options['verbosity']
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
                'worker_ttl': options['worker_ttl'],
                'serializer': options['serializer'],
            }
            w = get_worker(*args, **worker_kwargs)

            # Close any opened DB connection before any fork
            reset_db_connections()

            w.work(
                burst=options.get('burst', False),
                with_scheduler=options.get('with_scheduler', False),
                logging_level=level,
                max_jobs=options['max_jobs'],
                max_idle_time=options['max_idle_time'],
            )
        except ConnectionError as e:
            self.stderr.write(str(e))
            sys.exit(1)
