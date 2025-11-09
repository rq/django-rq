import warnings
from typing import Any, Callable, Optional, Union

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from redis import Redis
from rq.job import Job
from rq.queue import Queue
from rq.utils import import_attribute

from . import thread_queue
from .connection_utils import (
    filter_connection_params,
    get_connection,
    get_redis_connection,
)
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

    if isinstance(queue_class, str):
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

        super().__init__(*args, **kwargs)

    def original_enqueue_call(self, *args, **kwargs):
        queue_name = kwargs.get('queue_name') or self.name
        kwargs['result_ttl'] = kwargs.get('result_ttl', get_result_ttl(queue_name))

        return super().enqueue_call(*args, **kwargs)

    def enqueue_call(self, *args, **kwargs):
        if self._autocommit:
            return self.original_enqueue_call(*args, **kwargs)
        else:
            thread_queue.add(self, args, kwargs)


def get_queue(
    name: str = 'default',
    default_timeout: Optional[int] = None,
    is_async: Optional[bool] = None,
    autocommit: Optional[bool] = None,
    connection: Optional[Redis] = None,
    queue_class: Optional[Union[str, type[DjangoRQ]]] = None,
    job_class: Optional[Union[str, type[Job]]] = None,
    serializer: Any = None,
    **kwargs: Any,
) -> DjangoRQ:
    """
    Returns an rq Queue using parameters defined in ``RQ_QUEUES``
    """
    from .settings import QUEUES

    if kwargs.get('async') is not None:
        is_async = kwargs['async']
        warnings.warn('The `async` keyword is deprecated. Use `is_async` instead', DeprecationWarning)

    # If is_async is provided, use it, otherwise, get it from the configuration
    if is_async is None:
        is_async = QUEUES[name].get('ASYNC', True)
    # same for job_class
    job_class = get_job_class(job_class)

    if default_timeout is None:
        default_timeout = QUEUES[name].get('DEFAULT_TIMEOUT')
    if connection is None:
        connection = get_connection(name)
    if serializer is None:
        serializer = QUEUES[name].get('SERIALIZER')
    queue_class = get_queue_class(QUEUES[name], queue_class)
    return queue_class(
        name,
        default_timeout=default_timeout,
        connection=connection,
        is_async=is_async,
        job_class=job_class,
        autocommit=autocommit,
        serializer=serializer,
        **kwargs,
    )


def get_queue_by_index(index):
    """
    Returns an rq Queue using parameters defined in ``QUEUES_LIST``
    """
    from .settings import QUEUES_LIST

    config = QUEUES_LIST[int(index)]
    return get_queue_class(config)(
        config['name'],
        connection=get_redis_connection(config['connection_config']),
        is_async=config.get('ASYNC', True),
        serializer=config['connection_config'].get('SERIALIZER'),
    )


def get_scheduler_by_index(index):
    """
    Returns an rq-scheduler Scheduler using parameters defined in ``QUEUES_LIST``
    """
    from .settings import QUEUES_LIST

    config = QUEUES_LIST[int(index)]
    return get_scheduler(config['name'])


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
            raise ValueError(f'Queues must have the same class."{name}" and "{queue_names[0]}" have different classes')
        if connection_params != filter_connection_params(QUEUES[name]):
            raise ValueError(
                f'Queues must have the same redis connection."{name}" and "{queue_names[0]}" have different connections'
            )
        queues.append(queue)

    return queues


def enqueue(func: Callable, *args, **kwargs) -> Job:
    """
    A convenience function to put a job in the default queue. Usage::

    from django_rq import enqueue
    enqueue(func, *args, **kwargs)
    """
    return get_queue().enqueue(func, *args, **kwargs)


def get_result_ttl(name: str = 'default'):
    """
    Returns the result ttl from RQ_QUEUES if found, otherwise from RQ
    """
    from .settings import QUEUES

    RQ = getattr(settings, 'RQ', {})
    return QUEUES[name].get('DEFAULT_RESULT_TTL', RQ.get('DEFAULT_RESULT_TTL'))


"""
If rq_scheduler is installed, provide a ``get_scheduler`` function that
behaves like ``get_connection``, except that it returns a ``Scheduler``
instance instead of a ``Queue`` instance.
"""
try:
    from rq_scheduler import Scheduler

    class DjangoScheduler(Scheduler):
        """
        Use settings ``DEFAULT_RESULT_TTL`` from ``RQ``
        and ``DEFAULT_TIMEOUT`` from ``RQ_QUEUES`` if configured.
        """

        def _create_job(self, *args, **kwargs):
            from .settings import QUEUES

            if kwargs.get('timeout') is None:
                queue_name = kwargs.get('queue_name') or self.queue_name
                kwargs['timeout'] = QUEUES[queue_name].get('DEFAULT_TIMEOUT')

            if kwargs.get('result_ttl') is None:
                kwargs['result_ttl'] = getattr(settings, 'RQ', {}).get('DEFAULT_RESULT_TTL')

            return super()._create_job(*args, **kwargs)

    def get_scheduler(
        name: str = 'default',
        queue: Optional[DjangoRQ] = None,
        interval: int = 60,
        connection: Optional[Redis] = None,
    ) -> DjangoScheduler:
        """
        Returns an RQ Scheduler instance using parameters defined in
        ``RQ_QUEUES``
        """
        RQ = getattr(settings, 'RQ', {})
        scheduler_class = RQ.get('SCHEDULER_CLASS', DjangoScheduler)

        if isinstance(scheduler_class, str):
            scheduler_class = import_attribute(scheduler_class)

        if connection is None:
            connection = get_connection(name)

        if queue is None:
            queue = get_queue(name, connection=connection)

        return scheduler_class(
            queue_name=name, interval=interval, queue=queue, job_class=queue.job_class, connection=connection
        )

except ImportError:

    def get_scheduler(*args, **kwargs):  # type: ignore[misc]
        raise ImproperlyConfigured('rq_scheduler not installed')
