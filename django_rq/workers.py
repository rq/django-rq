from rq import Worker
from rq.utils import import_attribute

from .queues import get_queues, get_connection, filter_connection_params
from .settings import EXCEPTION_HANDLERS


def get_exception_handlers():
    """
    Custom exception handlers could be defined in settings.py:
    RQ = {
        'EXCEPTION_HANDLERS': ['path.to.handler'],
    }
    """
    return [import_attribute(path) for path in EXCEPTION_HANDLERS]


def get_worker(*queue_names):
    """
    Returns a RQ worker for all queues or specified ones.
    """
    queues = get_queues(*queue_names)
    return Worker(queues,
                  connection=queues[0].connection,
                  exception_handlers=get_exception_handlers() or None)


def collect_workers_by_connection(queues):
    """
    Collects, into a list, dictionaries of connections_config and its workers.

    This function makes an association between some configurarion and the
    workers it uses.
    What the return may looks like:

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
    workers_collections = []
    for item in queues:
        connection_params = filter_connection_params(item['connection_config'])
        if connection_params not in [c['config'] for c in workers_collections]:
            connection = get_connection(item['name'])
            collection = {
                'config': connection_params,
                'all_workers': Worker.all(connection=connection)
            }
            workers_collections.append(collection)
    return workers_collections


def get_all_workers_by_configuration(config, workers_collections):
    """
    Gets from a worker_collection the worker group associated to a given
    configuration
    """
    c = filter_connection_params(config)
    for collection in workers_collections:
        if c == collection['config']:
            return collection['all_workers']
