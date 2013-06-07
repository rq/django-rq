import threading


_thread_data = threading.local()


def get_queue():
    """
    Returns a temporary queue to store jobs before they're committed
    later in the request/responsce cycle. Each job is stored as a tuple
    containing the queue, args and kwargs.

    For example, if we call ``queue.enqueue_call(foo, kwargs={'bar': 'baz'})`` during the
    request/response cycle, job_queue will look like:

    job_queue = [(default_queue, foo, {'kwargs': {'bar': 'baz'}})]

    This implementation is heavily inspired by
    https://github.com/chrisdoble/django-celery-transactions
    """
    return _thread_data.__dict__.setdefault("job_queue", [])


def add(queue, args, kwargs):
    get_queue().append((queue, args, kwargs))


def commit(*args, **kwargs):
    """
    Processes all jobs in the delayed queue.
    """
    delayed_queue = get_queue()
    try:
        while delayed_queue:
            queue, args, kwargs = delayed_queue.pop(0)
            queue.original_enqueue_call(*args, **kwargs)
    finally:
        clear()


def clear(*args, **kwargs):
    try:
        del(_thread_data.job_queue)
    except AttributeError:
        pass
