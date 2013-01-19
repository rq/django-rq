from rq import Worker
from django.conf import settings

from .queues import get_queues


def get_worker(*queue_names):
    """
    Returns a RQ worker for all queues or specified ones.
    """
    queues = get_queues(*queue_names)
    w = Worker(queues, connection=queues[0].connection)
    if settings.RQ_SENTRY_DSN:
+       from raven import Client
+       from rq.contrib.sentry import register_sentry
        client = Client(settings.RQ_SENTRY_DSN)
        register_sentry(client, w)
    return w
