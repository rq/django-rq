from rq.decorators import job as _rq_job
from typing import TYPE_CHECKING, Union

from django.conf import settings

from .queues import get_queue

if TYPE_CHECKING:
    from rq import Queue


def job(func_or_queue, connection=None, *args, **kwargs):
    """
    The same as RQ's job decorator, but it automatically works out
    the ``connection`` argument from RQ_QUEUES.

    And also, it allows simplified ``@job`` syntax to put job into
    default queue.

    If RQ.DEFAULT_RESULT_TTL setting is set, it is used as default
    for ``result_ttl`` kwarg.
    """
    if callable(func_or_queue):
        func = func_or_queue
        queue: Union['Queue', str] = 'default'
    else:
        func = None
        queue = func_or_queue

    if isinstance(queue, str):
        try:
            queue = get_queue(queue)
            if connection is None:
                connection = queue.connection
        except KeyError:
            pass
    else:
        if connection is None:
            connection = queue.connection

    RQ = getattr(settings, 'RQ', {})
    default_result_ttl = RQ.get('DEFAULT_RESULT_TTL')
    if default_result_ttl is not None:
        kwargs.setdefault('result_ttl', default_result_ttl)

    kwargs['connection'] = connection
    decorator = _rq_job(queue, *args, **kwargs)
    if func:
        return decorator(func)
    return decorator
