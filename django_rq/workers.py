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


def collect_workers_per_configuration(queue_list):
    """
    Collects, into a list, dictionaries of connections_config and its workers.
    """
    workers_collections = []
    for item in queue_list:
        connection_params = filter_connection_params(item['connection_config'])
        if connection_params not in [c['config'] for c in workers_collections]:
            connection = get_connection(item['name'])
            collection = {
                'config': connection_params,
                'all_workers': Worker.all(connection=connection)
            }
            workers_collections.append(collection)
    return workers_collections
