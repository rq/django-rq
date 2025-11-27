from operator import itemgetter
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SHOW_ADMIN_LINK = getattr(settings, 'RQ_SHOW_ADMIN_LINK', False)

NAME = getattr(settings, 'RQ_NAME', 'default')
BURST: bool = getattr(settings, 'RQ_BURST', False)


def get_queues_list():
    """
    Build QUEUES_LIST from current RQ_QUEUES setting.

    Returns a list of queue configurations sorted by name.
    This ensures deterministic ordering across all calls.
    """
    queues = getattr(settings, 'RQ_QUEUES', {})
    return [{'name': queue_name, 'connection_config': config} for queue_name, config in sorted(queues.items())]


def get_queues_map():
    """
    Build QUEUES_MAP from current RQ_QUEUES setting.

    Returns a dict mapping queue name to its index in QUEUES_LIST.
    """
    queues_list = get_queues_list()
    return {q['name']: idx for idx, q in enumerate(queues_list)}


def __getattr__(name):
    """
    Provide dynamic access to QUEUES, QUEUES_LIST and QUEUES_MAP.

    This ensures settings changes (e.g., via override_settings in tests) are
    respected, and maintains backwards compatibility.
    """
    if name == 'QUEUES':
        queues = getattr(settings, 'RQ_QUEUES', None)
        if queues is None:
            raise ImproperlyConfigured("You have to define RQ_QUEUES in settings.py")
        return cast(dict[str, Any], queues)
    elif name == 'QUEUES_LIST':
        import warnings

        warnings.warn(
            "Importing QUEUES_LIST directly is deprecated. Use get_queues_list() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return get_queues_list()
    elif name == 'QUEUES_MAP':
        import warnings

        warnings.warn(
            "Importing QUEUES_MAP directly is deprecated. Use get_queues_map() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return get_queues_map()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Get exception handlers
EXCEPTION_HANDLERS: list[str] = getattr(settings, 'RQ_EXCEPTION_HANDLERS', [])

# Token for querying statistics
API_TOKEN: str = getattr(settings, 'RQ_API_TOKEN', '')
