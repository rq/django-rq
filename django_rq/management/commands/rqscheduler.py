from django.core.management.base import BaseCommand
from optparse import make_option
from django_rq import get_scheduler


class Command(BaseCommand):
    """
    Runs RQ scheduler
    """
    help = __doc__
    option_list = BaseCommand.option_list + (
        make_option(
            '--interval',
            type=int,
            dest='interval',
            default=60,
            help="How often the scheduler checks for new jobs to add to the "
                 "queue (in seconds).",
        ),
    )

    def handle(self, *args, **options):
        scheduler = get_scheduler(interval=options.get('interval'))
        scheduler.run()
