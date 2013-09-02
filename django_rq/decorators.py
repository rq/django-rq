from rq.decorators import job as _rq_job

from .queues import get_queue


def job(func_or_queue, connection=None, *args, **kwargs):
    """
    The same as RQ's job decorator, but it works automatically works out
    the ``connection`` argument from RQ_QUEUES.

    And also, it allows simplified ``@job`` syntax to put job into
    default queue.
    """
    if callable(func_or_queue):
        func = func_or_queue
        queue = 'default'
    else:
        func = None
        queue = func_or_queue

    try:
        from django.utils import six
        string_type = six.string_types
    except ImportError:
        # for django lt v1.5 and python 2
        string_type = basestring

    if isinstance(queue, string_type):
        try:
            queue = get_queue(queue)
            if connection is None:
                connection = queue.connection
        except KeyError:
            pass

    decorator = _rq_job(queue, connection=connection, *args, **kwargs)
    if func:
        return decorator(func)
    return decorator

