__version__ = "4.2.0"

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .connection_utils import get_connection
    from .decorators import job
    from .queues import enqueue, get_queue, get_scheduler
    from .workers import get_worker

# Import public helpers lazily so CLI startup can configure Django first: importing
# them eagerly reaches django_rq.settings, which reads Django settings at import time.
_EXPORT_MODULES = {
    "enqueue": "queues",
    "get_connection": "connection_utils",
    "get_queue": "queues",
    "get_scheduler": "queues",
    "get_worker": "workers",
    "job": "decorators",
}

__all__ = [
    "__version__",
    "enqueue",
    "get_connection",
    "get_queue",
    "get_scheduler",
    "get_worker",
    "job",
]


def __getattr__(name: str) -> Any:
    try:
        module_name = _EXPORT_MODULES[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value  # Later lookups find it here and skip __getattr__.
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
