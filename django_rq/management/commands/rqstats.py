import json

from django.core.management.base import BaseCommand
from django_rq.statistics import get_statistics


class Command(BaseCommand):
    """
    Print RQ statistics
    """
    help = __doc__

    def handle(self, *args, **options):
        print(json.dumps(get_statistics()))
