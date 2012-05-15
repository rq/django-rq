import redis
from rq import Queue


def get_connection(name='default'):
    """
    Returns a Redis connection to use based on parameters in settings.RQ_QUEUES
    """
    from .settings import QUEUES
    queue_config = QUEUES[name]
    return redis.Redis(host=queue_config['HOST'],
        port=queue_config['PORT'], db=queue_config['DB'])


def get_queue(name='default'):
    """
    Returns an rq Queue using parameters defined in ``RQ_QUEUES``
    """
    return Queue(name, connection=get_connection(name))


def enqueue(func, *args, **kwargs):
    '''
    A convenience function to put a job in the default queue. Usage::

    from django_rq import enqueue
    enqueue(func, *args, **kwargs)
    '''
    return get_queue().enqueue(func, *args, **kwargs)
