from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .queues import get_unique_connection_configs

QUEUES = getattr(settings, 'RQ_QUEUES', None)
if QUEUES is None:
    raise ImproperlyConfigured("You have to define RQ_QUEUES in settings.py")
NAME = getattr(settings, 'RQ_NAME', 'default')
BURST = getattr(settings, 'RQ_BURST', False)

# All queues in list format so we can get them by index, includes failed queues
QUEUES_LIST = []
for key, value in QUEUES.items():
    QUEUES_LIST.append({'name': key, 'connection_config': value})
for config in get_unique_connection_configs():
    QUEUES_LIST.append({'name': 'failed', 'connection_config': config})
