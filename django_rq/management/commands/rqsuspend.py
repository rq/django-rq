import logging
import sys

from django.core.management.base import BaseCommand
from rq.suspension import suspend

from ...queues import get_connection

log = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Suspend all queues."

    def add_arguments(self, parser):
        parser.add_argument(
            "--duration",
            "-d",
            type=int,
            help="The duration in seconds to suspend the workers.  If not provided, workers will be suspended indefinitely",
        )

    def handle(self, *args, **options):
        connection = get_connection()
        duration = options.get("duration")

        if duration is not None and duration < 1:
            log.error("Duration must be an integer greater than 1")
            sys.exit(1)

        if duration:
            suspend(connection, duration)
            msg = f"Suspending workers for {duration} seconds.  No new jobs will be started during that time, but then will automatically resume"
            log.info(msg)
        else:
            suspend(connection)
            log.info("Suspending workers.  No new jobs will be started.  But current jobs will be completed")
