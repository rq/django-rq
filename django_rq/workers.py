from rq import Worker
from rq.utils import import_attribute

from django.conf import settings
from django.utils import six

from .jobs import get_job_class
from .queues import filter_connection_params, get_connection, get_queues


def get_exception_handlers():
    """
    Custom exception handlers could be defined in settings.py:
    RQ = {
        'EXCEPTION_HANDLERS': ['path.to.handler'],
    }
    """
    from .settings import EXCEPTION_HANDLERS

    return [import_attribute(path) for path in EXCEPTION_HANDLERS]


def get_worker_class(worker_class=None):
    """
    Return worker class from RQ settings, otherwise return Worker.
    If `worker_class` is not None, it is used as an override (can be
    python import path as string).
    """
    RQ = getattr(settings, 'RQ', {})

    if worker_class is None:
        worker_class = Worker
        if 'WORKER_CLASS' in RQ:
            worker_class = RQ.get('WORKER_CLASS')

    if isinstance(worker_class, six.string_types):
        worker_class = import_attribute(worker_class)
    return worker_class


def get_worker(*queue_names, **kwargs):
    """
    Returns a RQ worker for all queues or specified ones.
    """
    job_class = get_job_class(kwargs.pop('job_class', None))
    queue_class = kwargs.pop('queue_class', None)
    queues = get_queues(*queue_names, **{'job_class': job_class,
                                         'queue_class': queue_class})
    # normalize queue_class to what get_queues returns
    queue_class = queues[0].__class__
    worker_class = get_worker_class(kwargs.pop('worker_class', None))
    return worker_class(queues,
                        connection=queues[0].connection,
                        exception_handlers=get_exception_handlers() or None,
                        job_class=job_class,
                        queue_class=queue_class,
                        **kwargs)
