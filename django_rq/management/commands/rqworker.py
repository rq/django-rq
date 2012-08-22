from django.core.management.base import BaseCommand

from rq import Worker
from redis.exceptions import ConnectionError

from django_rq.queues import get_queues


class Command(BaseCommand):
    """
    Runs RQ workers on specified queues. Note that all queues passed into a
    single rqworker command must share the same connection.

    Example usage:
    python manage.py rqworker high medium low
    """
    args = '<queue queue ...>'

    def handle(self, *args, **options):
        queues = get_queues(*args)
        try:
            w = Worker(queues, connection=queues[0].connection)
            w.work()
        except ConnectionError as e:
            print(e)
