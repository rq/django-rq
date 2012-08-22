from rq import Worker

from .queues import get_queues


def get_worker(*queue_names):
    """
    Returns a RQ worker for all queues or specified ones.
    """
    queues = get_queues(*queue_names)
    return Worker(queues, connection=queues[0].connection)
