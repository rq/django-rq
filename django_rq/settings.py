from operator import itemgetter
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SHOW_ADMIN_LINK = getattr(settings, 'RQ_SHOW_ADMIN_LINK', False)

QUEUES = cast(dict[str, Any], getattr(settings, 'RQ_QUEUES', None))
if QUEUES is None:
    raise ImproperlyConfigured("You have to define RQ_QUEUES in settings.py")
NAME = getattr(settings, 'RQ_NAME', 'default')
BURST: bool = getattr(settings, 'RQ_BURST', False)

# All queues in list format so we can get them by index, includes failed queues
QUEUES_LIST = []
QUEUES_MAP = {}
for key, value in sorted(QUEUES.items(), key=itemgetter(0)):
    QUEUES_LIST.append({'name': key, 'connection_config': value})
    QUEUES_MAP[key] = len(QUEUES_LIST) - 1

# Get exception handlers
EXCEPTION_HANDLERS: list[str] = getattr(settings, 'RQ_EXCEPTION_HANDLERS', [])

# Token for querying statistics
API_TOKEN: str = getattr(settings, 'RQ_API_TOKEN', '')
