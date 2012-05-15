from django.conf import settings

DEFAULT_QUEUES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
    }
}

QUEUES = getattr(settings, 'RQ_QUEUES', DEFAULT_QUEUES)
NAME = getattr(settings, 'RQ_NAME', 'default')
BURST = getattr(settings, 'RQ_BURST', False)