from django.core.management.base import BaseCommand

from django.utils.six.moves import input

from django_rq import get_queue


class Command(BaseCommand):
    """
    Flushes the queue specified as argument
    """
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            '--noinput', '--no-input', action='store_false',
            dest='interactive', default=True,
            help='Tells Django to NOT prompt the user for input of any kind.',
        )
        parser.add_argument('--queue', '-q', dest='queue', default='default',
                            help='Specify the queue [default]')

    def handle(self, *args, **options):
        verbosity = int(options.get('verbosity', 1))
        interactive = options['interactive']
        queue = get_queue(options.get('queue'))

        if interactive:
            confirm = input("""You have requested a flush the "%s" queue.
Are you sure you want to do this?

    Type 'yes' to continue, or 'no' to cancel: """ % queue.name)
        else:
            confirm = 'yes'

        if confirm == 'yes':
            queue.empty()
            if verbosity:
                print('Queue "%s" flushed.' % queue.name)
        else:
            if verbosity:
                print("Flush cancelled.")
