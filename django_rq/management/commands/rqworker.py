from django.core.management.base import BaseCommand

from redis.exceptions import ConnectionError

from django_rq.workers import get_worker


class Command(BaseCommand):
    """
    Runs RQ workers on specified queues. Note that all queues passed into a
    single rqworker command must share the same connection.

    Example usage:
    python manage.py rqworker high medium low
    """
    args = '<queue queue ...>'

    def handle(self, *args, **options):
        try:
            w = get_worker(*args)
            w.work()
        except ConnectionError as e:
            print(e)
