import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from functools import cached_property
from typing import Any, Callable, Optional, cast

from redis import Redis
from rq.cron import CronJob, CronScheduler
from rq.utils import as_text

from .connection_utils import get_connection, get_redis_connection, get_unique_connection_configs
from .settings import get_queues_map

# `CronJob.get_job_ids()` and the job history sorted set backing it were added in RQ 2.11
CRON_JOB_HISTORY_SUPPORTED = hasattr(CronJob, 'get_job_ids')


def get_cron_job_history(
    cron_job: CronJob, connection: Redis, start: int = 0, end: int = -1
) -> list[tuple[str, datetime]]:
    """
    Returns (job_id, enqueued_at) pairs for jobs spawned by `cron_job`, newest first.

    RQ records spawned jobs in a sorted set scored by the job's enqueue time. The history
    outlives the jobs themselves (entries are kept for a year, while a successful job's data
    is deleted once its `result_ttl` expires), so the score is the only way to tell when an
    already deleted job ran.

    `start` and `end` are zero based inclusive indexes into the newest first ordering,
    following `zrange` semantics (`end=-1` means the oldest entry).

    Returns an empty list on RQ < 2.11, which doesn't keep a job history.
    """
    if not CRON_JOB_HISTORY_SUPPORTED:
        return []

    entries = connection.zrange(cron_job.job_history_key, start, end, desc=True, withscores=True)
    return [(as_text(job_id), datetime.fromtimestamp(score, tz=timezone.utc)) for job_id, score in entries]


def get_cron_job_data(cron_job: CronJob, queues_map: Optional[dict[str, int]] = None) -> dict[str, Any]:
    """
    Returns a dict describing `cron_job` for display purposes.

    `queue_index` is None when the cron job's queue is not present in RQ_QUEUES, in which case
    the dashboard can't link to that queue's views.
    """
    if queues_map is None:
        queues_map = get_queues_map()

    if cron_job.cron:
        schedule = f"Cron: {cron_job.cron}"
    elif cron_job.interval is not None:
        schedule = f"Every {cron_job.interval} seconds"
    else:
        schedule = "-"

    job_options = cron_job.job_options
    options: list[str] = []
    for key in ('job_timeout', 'result_ttl', 'ttl', 'failure_ttl'):
        value = job_options.get(key)
        if value is not None:
            options.append(f"{key}={value}")

    return {
        # `name` identifies the job history and defaults to func_name on RQ >= 2.11.
        # Older versions don't have it at all.
        "name": getattr(cron_job, 'name', None) or cron_job.func_name,
        "func_name": cron_job.func_name,
        "queue_name": cron_job.queue_name,
        "queue_index": queues_map.get(cron_job.queue_name),
        "schedule": schedule,
        "latest_enqueue_time": cron_job.latest_enqueue_time,
        "next_enqueue_time": cron_job.next_enqueue_time,
        "args": cron_job.args,
        "kwargs": cron_job.kwargs,
        "meta": job_options.get('meta'),
        # Job options are exposed both individually, for pages that lay them out as fields, and
        # pre-formatted as `options`, for the cron scheduler table's single column
        "job_timeout": job_options.get('job_timeout'),
        "result_ttl": job_options.get('result_ttl'),
        "ttl": job_options.get('ttl'),
        "failure_ttl": job_options.get('failure_ttl'),
        "options": options,
        "webhooks": job_options.get('webhooks') or [],
    }


def get_cron_job_history_count(cron_job: CronJob, connection: Redis) -> int:
    """Returns the number of jobs recorded in `cron_job`'s history (0 on RQ < 2.11)."""
    if not CRON_JOB_HISTORY_SUPPORTED:
        return 0

    return connection.zcard(cron_job.job_history_key)


class DjangoCronScheduler(CronScheduler):
    """
    A Django-RQ bridge for RQ's CronScheduler that integrates with django_rq's
    queue configuration system.

    Key differences from RQ's CronScheduler:
    - Can be initialized with or without a connection parameter
    - If no connection provided, connection is set dynamically when the first job is registered
    - Validates that all registered jobs use queues with the same Redis connection
    - Integrates with RQ_QUEUES configuration from Django settings
    """

    _connection_config: Optional[dict[str, Any]]

    def __init__(
        self,
        connection: Optional[Redis] = None,
        logging_level: int = logging.INFO,
        name: str = '',
    ):
        """
        Initialize DjangoCronScheduler with optional Redis connection.

        If connection is not provided, it will be set when the first job is registered via register().

        Args:
            connection: Optional Redis connection instance
            logging_level: Logging level for the scheduler
            name: Optional name for the scheduler instance
        """
        # Call parent __init__ with the provided connection (or None)
        super().__init__(connection=cast(Redis, connection), logging_level=logging_level, name=name)

        # Track our django_rq specific state
        if connection is not None:
            self._connection_config = self._get_connection_config(connection)
        else:
            self._connection_config = None

    def _get_connection_config(self, connection: Redis) -> dict[str, Any]:
        """
        Extract Redis connection configuration to compare connections.

        Args:
            connection: Redis connection instance

        Returns:
            Dictionary of connection parameters for comparison
        """
        kwargs = connection.connection_pool.connection_kwargs

        # Only compare essential connection parameters that determine if
        # two connections are to the same Redis instance
        essential_params = ['host', 'port', 'db', 'username', 'password']
        return {key: kwargs.get(key) for key in essential_params if key in kwargs}

    def register(
        self,
        func: Callable[..., Any],
        queue_name: str,
        args: Optional[tuple[Any, ...]] = None,
        kwargs: Optional[dict[str, Any]] = None,
        interval: Optional[int] = None,
        cron: Optional[str] = None,
        job_timeout: Optional[int] = None,
        result_ttl: int = 500,
        ttl: Optional[int] = None,
        failure_ttl: Optional[int] = None,
        meta: Optional[dict[str, Any]] = None,
        webhooks: Optional[Sequence[Any]] = None,
        name: str = '',
    ):
        """
        Register a function to be run at regular intervals.

        On first call, this sets the Redis connection for the scheduler.
        Subsequent calls validate that the queue uses the same Redis connection.

        Args:
            func: Function to be scheduled
            queue_name: Name of the django_rq queue (must exist in RQ_QUEUES)
            args: Arguments to pass to the function
            kwargs: Keyword arguments to pass to the function
            interval: Interval in seconds (mutually exclusive with cron)
            cron: Cron expression (mutually exclusive with interval)
            job_timeout: Job timeout in seconds
            result_ttl: How long to keep job results
            ttl: Job time-to-live
            failure_ttl: How long to keep failed job info
            meta: Additional job metadata
            webhooks: Webhooks to attach to the job (requires rq >= 2.10)
            name: Optional name identifying this cron job (requires rq >= 2.11). Defaults to
                the function's import path. Cron jobs sharing a name share a job history.

        Returns:
            CronJob instance

        Raises:
            ValueError: If queue not found or uses different Redis connection
        """
        # Get connection for this queue
        connection = get_connection(queue_name)
        current_config = self._get_connection_config(connection)

        if self._connection_config:
            # Validate that this queue uses the same Redis connection
            if current_config != self._connection_config:
                raise ValueError(
                    f"Queue '{queue_name}' uses a different Redis connection than previously "
                    + 'registered queues. All jobs in a DjangoCronScheduler instance must use '
                    + 'queues with the same Redis connection.'
                )
        else:
            # First registration - set connection
            self.connection = connection
            self._connection_config = current_config
            # Clear cached_property so it recalculates with new connection
            if 'connection_index' in self.__dict__:
                del self.__dict__['connection_index']

        # Now call parent register method. `webhooks` and `name` are only passed along when
        # set, since CronScheduler.register() only accepts them on rq >= 2.10 and >= 2.11
        extra_kwargs: dict[str, Any] = {}
        if webhooks is not None:
            extra_kwargs['webhooks'] = webhooks
        if name:
            extra_kwargs['name'] = name
        return super().register(
            func=func,
            queue_name=queue_name,
            args=args,
            kwargs=kwargs,
            interval=interval,
            cron=cron,
            job_timeout=job_timeout,
            result_ttl=result_ttl,
            ttl=ttl,
            failure_ttl=failure_ttl,
            meta=meta,
            **extra_kwargs,
        )

    @cached_property
    def connection_index(self) -> int:
        """
        Returns the index of this scheduler's Redis connection in the unique connection configs list.

        This allows identifying which connection the scheduler is using, which can be useful for
        monitoring and management purposes (e.g., identifying schedulers by connection_index).

        Returns:
            The index of the connection in get_unique_connection_configs()

        Raises:
            ValueError: If no connection has been set yet (before first register() call),
                       or if the connection config cannot be found in unique configs
        """
        if not self._connection_config:
            raise ValueError('No connection has been set for this scheduler yet.')

        unique_configs = get_unique_connection_configs()

        # Find which index matches our connection by comparing essential params
        for i, unique_config in enumerate(unique_configs):
            conn = get_redis_connection(unique_config)
            config = self._get_connection_config(conn)

            # If it matches our connection config, this is our index
            if config == self._connection_config:
                return i

        # This should never happen - if we have a connection_config, it must be in the list
        raise ValueError('Could not find matching connection config in unique configs.')

    def get_jobs_data(self) -> list[dict[str, Any]]:
        """Returns a list of dicts describing each registered cron job for display purposes."""
        queues_map = get_queues_map()
        return [get_cron_job_data(job, queues_map) for job in self.get_jobs()]

    @classmethod
    def all(cls, connection: Redis, cleanup: bool = True) -> list['DjangoCronScheduler']:  # type: ignore[override]
        """
        Returns all DjangoCronScheduler instances from the registry.

        Args:
            connection: Redis connection to use
            cleanup: If True, removes stale entries from registry before fetching schedulers

        Returns:
            List of DjangoCronScheduler instances
        """
        return super().all(connection, cleanup)  # type: ignore[return-value]
