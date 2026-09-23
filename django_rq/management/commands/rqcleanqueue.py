from django.core.management.base import BaseCommand

from ... import get_queue


class Command(BaseCommand):
    """
    Clean queue.
    """
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--queue', '-q', dest='queue', default='default',
                            help='Specify the queue [default]')

    def handle(self, *args, **options):
        """
        Clean given queue.
        """
        verbosity = int(options.get('verbosity', 1))
        queue = get_queue(options.get('queue'))
        queue.empty()
        if verbosity:
            print('Queue %s cleaned' % options.get('queue'))
