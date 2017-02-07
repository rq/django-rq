import rq
from rq.utils import import_attribute

from .queues import get_queues
from .settings import EXCEPTION_HANDLERS

from django.db import close_old_connections, reset_queries


class DjangoWorker(rq.Worker):
    def perform_job(self, job, queue):
        reset_queries()
        close_old_connections()
        try:
            super(DjangoWorker, self).perform_job(job, queue)
        finally:
            close_old_connections()


def get_exception_handlers():
    """
    Custom exception handlers could be defined in settings.py:
    RQ = {
        'EXCEPTION_HANDLERS': ['path.to.handler'],
    }
    """
    return [import_attribute(path) for path in EXCEPTION_HANDLERS]


def get_worker(*queue_names):
    """
    Returns a RQ worker for all queues or specified ones.
    """
    queues = get_queues(*queue_names)
    return DjangoWorker(queues,
                        connection=queues[0].connection,
                        exception_handlers=get_exception_handlers() or None)
