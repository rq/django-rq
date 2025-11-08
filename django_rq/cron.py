import logging
from typing import Any, Callable, Optional, cast

from redis import Redis
from rq.cron import CronScheduler

from .connection_utils import get_connection


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
        timeout: Optional[int] = None,
        result_ttl: int = 500,
        ttl: Optional[int] = None,
        failure_ttl: Optional[int] = None,
        meta: Optional[dict[str, Any]] = None,
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
            timeout: Job timeout in seconds
            result_ttl: How long to keep job results
            ttl: Job time-to-live
            failure_ttl: How long to keep failed job info
            meta: Additional job metadata

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

        # Now call parent register method
        return super().register(
            func=func,
            queue_name=queue_name,
            args=args,
            kwargs=kwargs,
            interval=interval,
            cron=cron,
            timeout=timeout,
            result_ttl=result_ttl,
            ttl=ttl,
            failure_ttl=failure_ttl,
            meta=meta,
        )
