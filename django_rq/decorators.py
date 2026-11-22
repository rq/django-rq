from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ParamSpec, Protocol, TypeVar, overload

from django.conf import settings
from rq.decorators import job as _rq_job

from .queues import get_queue, get_result_ttl

if TYPE_CHECKING:
    from redis import Redis
    from rq import Queue

    P = ParamSpec('P')
    R = TypeVar('R', covariant=True)

    class _JobFn(Protocol[P, R]):
        def delay(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
        def enqueue(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
        def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...


@overload
def job(func_or_queue: Callable[P, R]) -> _JobFn[P, R]: ...


@overload
def job(
    func_or_queue: Queue | str,
    connection: Redis | None = None,
    *args: Any,
    **kwargs: Any,
) -> Callable[[Callable[P, R]], _JobFn[P, R]]: ...


def job(
    func_or_queue: Callable[P, R] | Queue | str,
    connection: Redis | None = None,
    *args: Any,
    **kwargs: Any,
) -> _JobFn[P, R] | Callable[[Callable[P, R]], _JobFn[P, R]]:
    """
    The same as RQ's job decorator, but it automatically works out
    the ``connection`` argument from RQ_QUEUES.

    And also, it allows simplified ``@job`` syntax to put job into
    default queue.

    If ``result_ttl`` is not passed, It set the default ttl to the queue `DEFAULT_RESULT_TTL`.
    """
    if callable(func_or_queue):
        func = func_or_queue
        queue: Queue | str = 'default'
    else:
        func = None
        queue = func_or_queue

    queue_name = 'default'
    if isinstance(queue, str):
        queue_name = queue
        try:
            queue = get_queue(queue)
            if connection is None:
                connection = queue.connection
        except KeyError:
            pass
    else:
        if queue.name in settings.RQ_QUEUES:
            queue_name = queue.name
        if connection is None:
            connection = queue.connection

    kwargs['result_ttl'] = kwargs.get('result_ttl', get_result_ttl(queue_name))
    kwargs['connection'] = connection
    decorator = _rq_job(queue, *args, **kwargs)
    if func:
        return decorator(func)
    return decorator
