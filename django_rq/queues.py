import redis
from rq.queue import FailedQueue, Queue
from rq.utils import import_attribute

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import six
from django_rq import thread_queue

from .jobs import get_job_class


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


def get_queue_class(config=None, queue_class=None):
    """
    Return queue class from config or from RQ settings, otherwise return DjangoRQ.
    If ``queue_class`` is provided, it takes priority.

    The full priority list for queue class sources:
    1. ``queue_class`` argument
    2. ``QUEUE_CLASS`` in ``config`` argument
    3. ``QUEUE_CLASS`` in base settings (``RQ``)
    """
    RQ = getattr(settings, 'RQ', {})
    if queue_class is None:
        queue_class = RQ.get('QUEUE_CLASS', DjangoRQ)
        if config:
            queue_class = config.get('QUEUE_CLASS', queue_class)

    if isinstance(queue_class, six.string_types):
        queue_class = import_attribute(queue_class)
    return queue_class


class DjangoRQ(Queue):
    """
    A subclass of RQ's QUEUE that allows jobs to be stored temporarily to be
    enqueued later at the end of Django's request/response cycle.
    """

    def __init__(self, *args, **kwargs):
        autocommit = kwargs.pop('autocommit', None)
        self._autocommit = get_commit_mode() if autocommit is None else autocommit

        super(DjangoRQ, self).__init__(*args, **kwargs)

    def original_enqueue_call(self, *args, **kwargs):
        return super(DjangoRQ, self).enqueue_call(*args, **kwargs)

    def enqueue_call(self, *args, **kwargs):
        if self._autocommit:
            return self.original_enqueue_call(*args, **kwargs)
        else:
            thread_queue.add(self, args, kwargs)


def get_redis_connection(config, use_strict_redis=False):
    """
    Returns a redis connection from a connection config
    """
    redis_cls = redis.StrictRedis if use_strict_redis else redis.Redis

    if 'URL' in config:
        return redis_cls.from_url(config['URL'], db=config.get('DB'))
    if 'USE_REDIS_CACHE' in config.keys():

        try:
            from django.core.cache import caches
            cache = caches[config['USE_REDIS_CACHE']]
        except ImportError:
            from django.core.cache import get_cache
            cache = get_cache(config['USE_REDIS_CACHE'])

        if hasattr(cache, 'client'):
            # We're using django-redis. The cache's `client` attribute
            # is a pluggable backend that return its Redis connection as
            # its `client`
            try:
                # To get Redis connection on django-redis >= 3.4.0
                # we need to use cache.client.get_client() instead of
                # cache.client.client used in older versions
                try:
                    return cache.client.get_client()
                except AttributeError:
                    return cache.client.client
            except NotImplementedError:
                pass
        else:
            # We're using django-redis-cache
            try:
                return cache._client
            except AttributeError:
                # For django-redis-cache > 0.13.1
                return cache.get_master_client()

    if 'UNIX_SOCKET_PATH' in config:
        return redis_cls(unix_socket_path=config['UNIX_SOCKET_PATH'], db=config['DB'])

    return redis_cls(host=config['HOST'], port=config['PORT'], db=config['DB'], password=config.get('PASSWORD', None))


def get_connection(name='default', use_strict_redis=False):
    """
    Returns a Redis connection to use based on parameters in settings.RQ_QUEUES
    """
    from .settings import QUEUES
    return get_redis_connection(QUEUES[name], use_strict_redis)


def get_connection_by_index(index):
    """
    Returns a Redis connection to use based on parameters in settings.RQ_QUEUES
    """
    from .settings import QUEUES_LIST
    return get_redis_connection(QUEUES_LIST[index]['connection_config'])


def get_queue(name='default', default_timeout=None, async=None,
              autocommit=None, queue_class=None, job_class=None, **kwargs):
    """
    Returns an rq Queue using parameters defined in ``RQ_QUEUES``
    """
    from .settings import QUEUES

    # If async is provided, use it, otherwise, get it from the configuration
    if async is None:
        async = QUEUES[name].get('ASYNC', True)
    # same for job_class
    job_class = get_job_class(job_class)

    if default_timeout is None:
        default_timeout = QUEUES[name].get('DEFAULT_TIMEOUT')
    queue_class = get_queue_class(QUEUES[name], queue_class)
    return queue_class(name, default_timeout=default_timeout,
                       connection=get_connection(name), async=async,
                       job_class=job_class, autocommit=autocommit, **kwargs)


def get_queue_by_index(index):
    """
    Returns an rq Queue using parameters defined in ``QUEUES_LIST``
    """
    from .settings import QUEUES_LIST
    config = QUEUES_LIST[int(index)]
    if config['name'] == 'failed':
        return FailedQueue(connection=get_redis_connection(config['connection_config']))
    return get_queue_class(config)(
        config['name'],
        connection=get_redis_connection(config['connection_config']),
        async=config.get('ASYNC', True))


def get_failed_queue(name='default'):
    """
    Returns the rq failed Queue using parameters defined in ``RQ_QUEUES``
    """
    return FailedQueue(connection=get_connection(name))


def filter_connection_params(queue_params):
    """
    Filters the queue params to keep only the connection related params.
    """
    CONNECTION_PARAMS = ('URL', 'DB', 'USE_REDIS_CACHE',
                         'UNIX_SOCKET_PATH', 'HOST', 'PORT', 'PASSWORD')

    #return {p:v for p,v in queue_params.items() if p in CONNECTION_PARAMS}
    # Dict comprehension compatible with python 2.6
    return dict((p,v) for (p,v) in queue_params.items() if p in CONNECTION_PARAMS)


def get_queues(*queue_names, **kwargs):
    """
    Return queue instances from specified queue names.
    All instances must use the same Redis connection.
    """
    from .settings import QUEUES

    if len(queue_names) <= 1:
        # Return "default" queue if no queue name is specified
        # or one queue with specified name
        return [get_queue(*queue_names, **kwargs)]

    # will return more than one queue
    # import job class only once for all queues
    kwargs['job_class'] = get_job_class(kwargs.pop('job_class', None))

    queue_params = QUEUES[queue_names[0]]
    connection_params = filter_connection_params(queue_params)
    queues = [get_queue(queue_names[0], **kwargs)]

    # do consistency checks while building return list
    for name in queue_names[1:]:
        queue = get_queue(name, **kwargs)
        if type(queue) is not type(queues[0]):
            raise ValueError(
                'Queues must have the same class.'
                '"{0}" and "{1}" have '
                'different classes'.format(name, queue_names[0]))
        if connection_params != filter_connection_params(QUEUES[name]):
            raise ValueError(
                'Queues must have the same redis connection.'
                '"{0}" and "{1}" have '
                'different connections'.format(name, queue_names[0]))
        queues.append(queue)

    return queues


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
        value = filter_connection_params(value)
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
