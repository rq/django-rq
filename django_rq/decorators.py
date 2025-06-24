from rq.decorators import job as _rq_job
from typing import Any, Callable, Optional, overload, Protocol, TYPE_CHECKING, TypeVar, Union

from .queues import get_queue, get_result_ttl


if TYPE_CHECKING:
    from redis import Redis
    from rq import Queue
    from typing_extensions import ParamSpec

    P = ParamSpec('P')
    R = TypeVar('R', covariant=True)

    class _JobFn(Protocol[P, R]):
        def delay(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
        def enqueue(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
        def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...


@overload
def job(func_or_queue: 'Callable[P, R]') -> '_JobFn[P, R]': ...

@overload
def job(
    func_or_queue: Union['Queue', str],
    connection: Optional['Redis'] = None,
    *args: Any,
    **kwargs: Any,
) -> Callable[['Callable[P, R]'], '_JobFn[P, R]']: ...


def job(
    func_or_queue: Union['Callable[P, R]', 'Queue', str],
    connection: Optional['Redis'] = None,
    *args: Any,
    **kwargs: Any,
) -> Union['_JobFn[P, R]', Callable[['Callable[P, R]'], '_JobFn[P, R]']]:
    """
    The same as RQ's job decorator, but it automatically works out
    the ``connection`` argument from RQ_QUEUES.

    And also, it allows simplified ``@job`` syntax to put job into
    default queue.

    If ``result_ttl`` is not passed, It set the default ttl to the queue `DEFAULT_RESULT_TTL`.
    """
    if callable(func_or_queue):
        func = func_or_queue
        queue: Union['Queue', str] = 'default'
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
        if connection is None:
            connection = queue.connection

    kwargs['result_ttl'] = kwargs.get('result_ttl', get_result_ttl(queue_name))
    kwargs['connection'] = connection
    decorator = _rq_job(queue, *args, **kwargs)
    if func:
        return decorator(func)
    return decorator
