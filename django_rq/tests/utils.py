from typing import Any, Dict
from unittest.mock import patch

from rq.exceptions import NoSuchJobError
from rq.job import Job

from django_rq.queues import get_connection, get_queue_by_index

try:
    from redis.backoff import ExponentialWithJitterBackoff, NoBackoff  # type: ignore[attr-defined]
    from redis.retry import Retry
except ImportError:
    ExponentialWithJitterBackoff = None
    Retry = None  # type: ignore[misc, assignment]


def _is_buggy_retry(kwargs: dict[str, Any]) -> bool:
    return (
        Retry is not None
        and (retry := kwargs.get('retry')) is not None
        and isinstance(retry, Retry)
        and isinstance(retry._backoff, ExponentialWithJitterBackoff)  # type: ignore[attr-defined]
    )


def get_queue_index(name='default'):
    """
    Returns the position of Queue for the named queue in QUEUES_LIST
    """
    connection = get_connection(name)
    connection_kwargs = connection.connection_pool.connection_kwargs

    for i in range(0, 100):
        try:
            q = get_queue_by_index(i)
        except AttributeError:
            continue
        if q.name == name:
            # assert that the connection is correct
            pool_kwargs = q.connection.connection_pool.connection_kwargs
            if not _is_buggy_retry(pool_kwargs) or not _is_buggy_retry(connection_kwargs):
                assert pool_kwargs == connection_kwargs
            else:
                # patch the retry backoff since there is a bug in the default
                # backoff strategy
                #
                # fixed in https://github.com/redis/redis-py/pull/3668
                with patch.object(pool_kwargs['retry'], '_backoff', NoBackoff()):
                    with patch.object(connection_kwargs['retry'], '_backoff', NoBackoff()):
                        assert pool_kwargs == connection_kwargs

                assert pool_kwargs['retry']._backoff.__dict__ == connection_kwargs['retry']._backoff.__dict__

            return i

    return None


def flush_registry(registry):
    """Helper function to flush a registry and delete all jobs in it."""
    connection = registry.connection
    for job_id in registry.get_job_ids():
        connection.zrem(registry.key, job_id)
        try:
            job = Job.fetch(job_id, connection=connection)
            job.delete()
        except NoSuchJobError:
            pass
