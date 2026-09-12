import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .queues import DjangoRQ

_thread_data = threading.local()


def get_queue():
    """
    Returns a temporary queue to store deferred enqueue calls before they're
    committed later in the request/response cycle. Each entry is a tuple of
    ``(queue, method_name, args, kwargs)`` where ``method_name`` is the RQ
    method to run on ``queue`` (``'enqueue_job'`` or ``'enqueue_at'``).

    For example, if we call ``queue.enqueue(foo, bar='baz')`` during the
    request/response cycle, job_queue will look like:

    job_queue = [(default_queue, 'enqueue_job', (<Job ...>,), {'pipeline': None, 'at_front': False, 'unique': False})]

    This implementation is heavily inspired by
    https://github.com/chrisdoble/django-celery-transactions
    """
    return _thread_data.__dict__.setdefault("job_queue", [])


def add(queue: 'DjangoRQ', method_name: str, args: tuple, kwargs: dict) -> None:
    get_queue().append((queue, method_name, args, kwargs))


def commit(*args: Any, **kwargs: Any) -> None:
    """
    Processes all deferred calls in the delayed queue.
    """
    delayed_queue = get_queue()
    try:
        while delayed_queue:
            queue, method_name, args, kwargs = delayed_queue.pop(0)
            queue.enqueue_now(method_name, *args, **kwargs)
    finally:
        clear()


def clear(*args: Any, **kwargs: Any) -> None:
    try:
        del _thread_data.job_queue
    except AttributeError:
        pass
