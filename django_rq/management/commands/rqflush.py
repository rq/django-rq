from django.core.management.base import BaseCommand

from django_rq import get_queue


class Command(BaseCommand):
    """
    Removes all queue jobs
    """
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--queue', '-q', dest='queue', default='default',
                            help='Specify the queue [default]')

    def handle(self, *args, **options):
        """
        Queues the function given with the first argument with the
        parameters given with the rest of the argument list.
        """
        verbosity = int(options.get('verbosity', 1))
        queue = get_queue(options.get('queue'))
        queue.empty()
        if verbosity:
            print('Queue "%s" cleaned' % queue.name)
