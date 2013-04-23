from django.core.exceptions import ImproperlyConfigured

import redis
from rq.queue import FailedQueue, Queue


def get_redis_connection(config):
    """
    Returns a redis connection from a connection config
    """
    if 'URL' in config:
        return redis.from_url(config['URL'], db=config['DB'])
    if 'USE_REDIS_CACHE' in config.keys():

        from django.core.cache import get_cache
        cache = get_cache(config['USE_REDIS_CACHE'])

        if hasattr(cache, 'client'):
            # We're using django-redis. The cache's `client` attribute
            # is a pluggable backend that return its Redis connection as
            # its `client`
            try:
                return cache.client.client
            except NotImplementedError:
                pass
        else:
            # We're using django-redis-cache
            return cache._client

    return redis.Redis(host=config['HOST'],
        port=config['PORT'], db=config['DB'],
        password=config.get('PASSWORD', None))


def get_connection(name='default'):
    """
    Returns a Redis connection to use based on parameters in settings.RQ_QUEUES
    """
    from .settings import QUEUES
    return get_redis_connection(QUEUES[name])


def get_connection_by_index(index):
    """
    Returns a Redis connection to use based on parameters in settings.RQ_QUEUES
    """
    from .settings import QUEUES_LIST
    return get_redis_connection(QUEUES_LIST[index]['connection_config'])


def get_queue(name='default', default_timeout=None, async=True):
    """
    Returns an rq Queue using parameters defined in ``RQ_QUEUES``
    """
    return Queue(name, default_timeout=default_timeout,
                 connection=get_connection(name), async=async)


def get_queue_by_index(index):
    """
    Returns an rq Queue using parameters defined in ``QUEUES_LIST``
    """
    from .settings import QUEUES_LIST    
    config = QUEUES_LIST[int(index)]
    if config['name'] == 'failed':
        return FailedQueue(connection=get_redis_connection(config['connection_config']))    
    return Queue(config['name'],
                 connection=get_redis_connection(config['connection_config']))


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


def get_unique_connection_configs(config=None):
    """
    Returns a list of unique Redis connections from config
    """
    if config is None:
        from .settings import QUEUES
        config = QUEUES

    connection_configs = []
    for key, value in config.items():
        if value not in connection_configs:
            connection_configs.append(value)
    return connection_configs


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
