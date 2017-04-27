from rq import Worker
from rq.utils import import_attribute

from .settings import EXCEPTION_HANDLERS
from .queues import get_queues


def get_exception_handlers(queue_name):
    """Custom exception handler defined in QUEUE settings:
    RQ_QUEUES = {
        'default': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
            'PASSWORD': '',
            'DEFAULT_TIMEOUT': 360,
            'EXCEPTION_HANDLERS': [
                'test_exception_handler.my_custom_exception'
            ],
        }
    }
    """

    if queue_name:
        return [import_attribute(exception_handler) for exception_handler in
                queue_name]
    else:
        return [import_attribute(path) for path in EXCEPTION_HANDLERS]


def get_worker(*queue_names):
    """
    Returns a RQ worker for all queues or specified ones.
    """
    queues = get_queues(*queue_names)
    exception_handlers = get_exception_handlers(queues[0].exception_handlers)

    if exception_handlers:
        return Worker(
            queues,
            connection=queues[0].connection,
            exception_handlers=exception_handlers
        )
    else:
        return Worker(queues, connection=queues[0].connection)
