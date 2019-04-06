from operator import itemgetter

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .queues import get_unique_connection_configs

SHOW_ADMIN_LINK = getattr(settings, 'RQ_SHOW_ADMIN_LINK', False)

QUEUES = getattr(settings, 'RQ_QUEUES', None)
if QUEUES is None:
    raise ImproperlyConfigured("You have to define RQ_QUEUES in settings.py")
NAME = getattr(settings, 'RQ_NAME', 'default')
BURST = getattr(settings, 'RQ_BURST', False)

# All queues in list format so we can get them by index, includes failed queues
QUEUES_LIST = []
for key, value in sorted(QUEUES.items(), key=itemgetter(0)):
    QUEUES_LIST.append({'name': key, 'connection_config': value})

# Get exception handlers
EXCEPTION_HANDLERS = getattr(settings, 'RQ_EXCEPTION_HANDLERS', [])

# Token for querying statistics
API_TOKEN = getattr(settings, 'RQ_API_TOKEN', '')
