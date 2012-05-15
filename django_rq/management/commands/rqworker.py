from django.core.management.base import BaseCommand

from rq import Queue, Worker
from redis.exceptions import ConnectionError

from django_rq import settings
from django_rq.queues import get_connection


class Command(BaseCommand):
    """
    RQ consumer
    """

    def handle(self, *args, **options):
        try:
            queues = [Queue(name, connection=get_connection(name)) for name in settings.QUEUES]
            for queue in queues:
                w = Worker([queue], connection=queue.connection)
                w.work(burst=settings.BURST)
        except ConnectionError as e:
            print(e)
