from django.core.management.base import BaseCommand

from rq import Queue, Worker
from redis.exceptions import ConnectionError

from django_rq import get_queue


def get_queues(*queue_names):
    """
    Return queue instances from specified queue names.
    All instances must use the same Redis connection.
    """
    from django_rq import settings
    if len(queue_names) > 1:
        connection_params = settings.QUEUES[queue_names[0]]
        for name in queue_names:
            if settings.QUEUES[name] != connection_params:
                raise ValueError('Queues in a single command must have the same '
                                 'redis connection. Queues "{0}" and "{1}" have '
                                 'different connections'.format(name, queue_names[0]))
    return [get_queue(name) for name in queue_names]


class Command(BaseCommand):
    """
    Runs RQ workers on specified queues. Note that all queues passed into a single rqworker
    command must share the same connection.

    Example usage:
    python manage.py rqworker high medium low
    """
    args = '<queue queue ...>'

    def handle(self, *args, **options):        
        if args:
            queues = get_queues(*args)
        else:
            from django_rq import settings
            queues = get_queues(*settings.QUEUES.keys())
        try:
            w = Worker(queues, connection=queues[0].connection)
            w.work()
        except ConnectionError as e:
            print(e)
