from django.core.management.base import BaseCommand

from ... import get_queue


class Command(BaseCommand):
    """
    Queue a function with the given arguments.
    """
    help = __doc__
    args = '<function arg arg ...>'

    def add_arguments(self, parser):
        parser.add_argument('--queue', '-q', dest='queue', default='default',
                            help='Specify the queue [default]')
        parser.add_argument('--timeout', '-t', type=int, dest='timeout',
                            help='A timeout in seconds')
        parser.add_argument('args', nargs='*')

    def handle(self, *args, **options):
        """
        Queues the function given with the first argument with the
        parameters given with the rest of the argument list.
        """
        verbosity = int(options.get('verbosity', 1))
        timeout = options.get('timeout')
        queue = get_queue(options.get('queue'))
        job = queue.enqueue_call(args[0], args=args[1:], timeout=timeout)
        if verbosity:
            print('Job %s created' % job.id)
