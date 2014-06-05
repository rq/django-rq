from django.core.management.base import BaseCommand
from optparse import make_option

from django_rq import get_queue


class Command(BaseCommand):
    """
    Queue a function with the given arguments.
    """
    help = __doc__
    args = '<function arg arg ...>'

    option_list = BaseCommand.option_list + (
        make_option('--queue', '-q', dest='queue', default='default',
            help='Specify the queue [default]'),
        make_option('--timeout', '-t', type='int', dest='timeout',
            help='A timeout in seconds'),
    )

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
