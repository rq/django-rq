from django.core.management.base import BaseCommand
from rq.suspension import resume

from ...queues import get_connection


class Command(BaseCommand):
    help = "Resume all queues."

    def handle(self, *args, **options):
        connection = get_connection()
        resume(connection)
