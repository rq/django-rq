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


def get_queues(*queue_names):
    """
    Return queue instances from specified queue names.
    All instances must use the same Redis connection.
    """
    from .settings import QUEUES
    if len(queue_names) == 0:
        # Return "default" queue if no queue name is specified
        return [get_queue()]
    if len(queue_names) > 1:
        connection_params = QUEUES[queue_names[0]]
        for name in queue_names:
            if QUEUES[name] != connection_params:
                raise ValueError(
                    'Queues in a single command must have the same '
                    'redis connection. Queues "{0}" and "{1}" have '
                    'different connections'.format(name, queue_names[0]))
    return [get_queue(name) for name in queue_names]


def enqueue(func, *args, **kwargs):
    """
    A convenience function to put a job in the default queue. Usage::

    from django_rq import enqueue
    enqueue(func, *args, **kwargs)
    """
    return get_queue().enqueue(func, *args, **kwargs)


"""
If rq_scheduler is installed, provide a ``get_scheduler`` function that
behaveslike ``get_connection``, except that it returns a ``Scheduler``
instance instead of a ``Queue`` instance.
"""
try:
    from rq_scheduler import Scheduler

    def get_scheduler(name='default'):
        """
        Returns an RQ Scheduler instance using parameters defined in
        ``RQ_QUEUES``
        """
        return Scheduler(name, connection=get_connection(name))
except ImportError:
    def get_scheduler(name='default'):
        raise ImproperlyConfigured('rq_scheduler not installed')
