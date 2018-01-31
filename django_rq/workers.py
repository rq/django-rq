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


def collect_workers_by_connection(queues):
    """
    Collects, into a list, dictionaries of connections_config and its workers.

    This function makes an association between some configuration and the
    workers it uses.
    What the return may look like:

        workers_collection = [
            {
                'config': {'DB': 0, 'PORT': 6379, 'HOST': 'localhost'},
                'all_workers': [worker1, worker2],
            },
            {
                'config': {'DB': 1, 'PORT': 6379, 'HOST': 'localhost'},
                'all_workers': [worker1]
            }
        ]

    Use `get_all_workers_by_configuration()` to select a worker group from the
    collection returned by this function.
    """
    worker_class = get_worker_class()

    workers_collections = []
    for item in queues:
        connection_params = filter_connection_params(item['connection_config'])
        if connection_params not in [c['config'] for c in workers_collections]:
            connection = get_connection(item['name'])
            collection = {
                'config': connection_params,
                'all_workers': worker_class.all(connection=connection)
            }
            workers_collections.append(collection)
    return workers_collections


def get_all_workers_by_configuration(config, workers_collections):
    """
    Gets from a worker_collection the worker group associated to a given
    connection configuration.
    """
    c = filter_connection_params(config)
    for collection in workers_collections:
        if c == collection['config']:
            return collection['all_workers']
