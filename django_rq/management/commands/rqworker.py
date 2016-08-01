import os
import sys
import importlib
import logging
import subprocess

from django.core.management.base import BaseCommand
from django.utils.autoreload import reloader_thread

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

    args = '<queue queue ...>'

    def add_arguments(self, parser):
        parser.add_argument('--worker-class', action='store', dest='worker_class',
                            default='rq.Worker', help='RQ Worker class to use')
        parser.add_argument('--pid', action='store', dest='pid',
                            default=None, help='PID file to write the worker`s pid into')
        parser.add_argument('--burst', action='store', dest='burst',
                            default=False, help='Run worker in burst mode')
        parser.add_argument('--name', action='store', dest='name',
                            default=None, help='Name of the worker')
        parser.add_argument('--queue-class', action='store', dest='queue_class',
                            default='django_rq.queues.DjangoRQ', help='Queues class to use')
        parser.add_argument('--worker-ttl', action='store', type=int,
                            dest='worker_ttl', default=420,
                            help='Default worker timeout to be used')
        parser.add_argument('--workers', '-w', action='store', type=int, dest='num_workers',
                            default=None, help='Number of workers to spawn, defaults to RQ_CONCURRENCY, or 1')
        parser.add_argument('--autoreload', action='store', type=bool, dest='autoreload',
                            default=False, help='Enable autoreload of rqworkers for development')

    def handle(self, *args, **options):

        pid = options.get('pid')
        if pid:
            with open(os.path.expanduser(pid), "w") as fp:
                fp.write(str(os.getpid()))

        if os.environ.get('RUN_MAIN') == 'true':
            try:
                self.create_worker(*args, **options)
            except KeyboardInterrupt:
                pass
        elif os.environ.get('RUN_RELOADER') == 'true':
            try:
                reloader_thread()
            except KeyboardInterrupt:
                pass
        else:
            num_workers = options['num_workers']
            if not num_workers:
                num_workers = int(os.environ.get('RQ_CONCURRENCY', 1))

            workers = []
            # need the number of workers - 1 because our main process will create one
            for _ in range(num_workers - 1):
                workers.append(self.create_worker_process())

            if options['autoreload']:
                workers.append(self.create_worker_process())
                self.create_reloader(workers)
            else:
                self.create_worker(*args, **options)

    def create_worker_process(self):
        args = [sys.executable] + ['-W%s' % o for o in sys.warnoptions] + sys.argv
        if sys.platform == "win32":
            args = ['"%s"' % arg for arg in args]
        new_environ = os.environ.copy()
        new_environ['RUN_MAIN'] = 'true'
        return subprocess.Popen(args, executable=sys.executable, env=new_environ)

    def create_reloader(self, workers):
        args = [sys.executable] + ['-W%s' % o for o in sys.warnoptions] + sys.argv
        if sys.platform == "win32":
            args = ['"%s"' % arg for arg in args]
        new_environ = os.environ.copy()
        new_environ['RUN_RELOADER'] = 'true'
        reloader = subprocess.Popen(args, executable=sys.executable, env=new_environ)
        try:
            reloader.wait()
        except KeyboardInterrupt:
            pass
        if reloader.returncode == 3:
            new_workers = []
            for worker in workers:
                worker.terminate()
                new_workers.append(self.create_worker_process())
            self.create_reloader(new_workers)
        else:
            for worker in workers:
                worker.terminate()
            sys.exit(reloader.returncode)

    def create_worker(self, *args, **options):
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

            # Call use_connection to push the redis connection into LocalStack
            # without this, jobs using RQ's get_current_job() will fail
            use_connection(w.connection)
            w.work(burst=options.get('burst', False))
        except ConnectionError as e:
            print(e)
