from django.core.exceptions import ImproperlyConfigured

import redis
from rq import Queue


def get_connection(name='default'):
    """
    Returns a Redis connection to use based on parameters in settings.RQ_QUEUES
    """
    from .settings import QUEUES
    queue_config = QUEUES[name]
    return redis.Redis(host=queue_config['HOST'],
        port=queue_config['PORT'], db=queue_config['DB'],
        password=queue_config.get('PASSWORD', None))


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


"""
If rq_scheduler is installed, provide a ``get_scheduler`` function that behaves
like ``get_connection``, except that it returns a ``Scheduler`` instance instead of
a ``Queue`` instance.
"""
try:
    from rq_scheduler import Scheduler
    def get_scheduler(name='default'):
        """
        Returns an RQ Scheduler instance using parameters defined in ``RQ_QUEUES``
        """
        return Scheduler(name, connection=get_connection(name))
except ImportError:
    def get_scheduler(name='default'):
        raise ImproperlyConfigured('rq_scheduler not installed')