from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

import redis
from rq.queue import FailedQueue, Queue

from django_rq import thread_queue


def get_commit_mode():
    """
    Disabling AUTOCOMMIT causes enqueued jobs to be stored in a temporary queue.
    Jobs in this queue are only enqueued after the request is completed and are
    discarded if the request causes an exception (similar to db transactions).

    To disable autocommit, put this in settings.py:
    RQ = {
        'AUTOCOMMIT': False,
    }
    """
    RQ = getattr(settings, 'RQ', {})
    return RQ.get('AUTOCOMMIT', True)


class DjangoRQ(Queue):
    """
    A subclass of RQ's QUEUE that allows jobs to be stored temporarily to be
    enqueued later at the end of Django's request/response cycle.
    """

    def __init__(self, *args, **kwargs):
        autocommit = kwargs.pop('autocommit', None)
        self._autocommit = get_commit_mode() if autocommit is None else autocommit
        return super(DjangoRQ, self).__init__(*args, **kwargs)

    def original_enqueue_call(self, *args, **kwargs):
        return super(DjangoRQ, self).enqueue_call(*args, **kwargs)

    def enqueue_call(self, *args, **kwargs):
        # print args, kwargs
        if self._autocommit:
            return self.original_enqueue_call(*args, **kwargs)
        else:
            thread_queue.add(self, args, kwargs)


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


def get_queue(name='default', default_timeout=None, async=None,
              autocommit=None):
    """
    Returns an rq Queue using parameters defined in ``RQ_QUEUES``
    """
    from .settings import QUEUES

    # If async is provided, use it, otherwise, get it from the configuration
    if async is None:
        async = QUEUES[name].get('ASYNC', True)

    return DjangoRQ(name, default_timeout=default_timeout,
                    connection=get_connection(name), async=async,
                    autocommit=autocommit)


def get_queue_by_index(index):
    """
    Returns an rq Queue using parameters defined in ``QUEUES_LIST``
    """
    from .settings import QUEUES_LIST
    config = QUEUES_LIST[int(index)]
    if config['name'] == 'failed':
        return FailedQueue(connection=get_redis_connection(config['connection_config']))
    return DjangoRQ(
        config['name'],
        connection=get_redis_connection(config['connection_config']),
        async=config.get('ASYNC', True))


def get_failed_queue(name='default'):
    """
    Returns the rq failed Queue using parameters defined in ``RQ_QUEUES``
    """
    return FailedQueue(connection=get_connection(name))


def get_queues(*queue_names, **kwargs):
    """
    Return queue instances from specified queue names.
    All instances must use the same Redis connection.
    """
    from .settings import QUEUES
    autocommit = kwargs.get('autocommit', None)
    if len(queue_names) == 0:
        # Return "default" queue if no queue name is specified
        return [get_queue(autocommit=autocommit)]
    if len(queue_names) > 1:
        connection_params = QUEUES[queue_names[0]]
        for name in queue_names:
            if QUEUES[name] != connection_params:
                raise ValueError(
                    'Queues must have the same redis connection.'
                    '"{0}" and "{1}" have '
                    'different connections'.format(name, queue_names[0]))
    return [get_queue(name, autocommit=autocommit) for name in queue_names]


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
behaves like ``get_connection``, except that it returns a ``Scheduler``
instance instead of a ``Queue`` instance.
"""
try:
    from rq_scheduler import Scheduler

    def get_scheduler(name='default', interval=60):
        """
        Returns an RQ Scheduler instance using parameters defined in
        ``RQ_QUEUES``
        """
        return Scheduler(name, interval=interval,
                         connection=get_connection(name))
except ImportError:
    def get_scheduler(*args, **kwargs):
        raise ImproperlyConfigured('rq_scheduler not installed')
