from typing import Any, Optional, Union

from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from redis.sentinel import SentinelConnectionPool
from rq.command import send_stop_job_command
from rq.executions import Execution
from rq.job import Job, JobStatus
from rq.queue import Queue
from rq.registry import (
    BaseRegistry,
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
    clean_registries,
)
from rq.worker import Worker
from rq.worker_registration import clean_worker_registry

from .connection_utils import get_connection, get_redis_connection, get_unique_connection_configs
from .cron import DjangoCronScheduler
from .queues import get_queue_by_index, get_scheduler
from .settings import get_queues_list
from .templatetags.django_rq import to_localtime


def get_scheduler_pid(queue: Queue) -> Union[bool, int, None]:
    '''Checks whether there's a scheduler-lock on a particular queue, and returns the PID.
    It Only works with RQ's Built-in RQScheduler.
    When RQ-Scheduler is available returns False
    If not, it checks the RQ's RQScheduler for a scheduler lock in the desired queue
    Note: result might have some delay (1-15 minutes) but it helps visualizing whether the setup is working correctly
    '''
    try:
        # first try get the rq-scheduler
        get_scheduler(queue.name)  # should fail if rq_scheduler not present
        return False  # Not possible to give useful information without creating a performance issue (redis.keys())
    except ImproperlyConfigured:
        from rq.scheduler import RQScheduler

        # When a scheduler acquires a lock it adds an expiring key: (e.g: rq:scheduler-lock:<queue.name>)
        # TODO: (RQ>= 1.13) return queue.scheduler_pid
        pid = queue.connection.get(RQScheduler.get_locking_key(queue.name))
        return int(pid.decode()) if pid is not None else None
    except Exception:
        pass  # Return None
    return None


_DISPLAYABLE_CONNECTION_KWARGS = (
    'host',
    'port',
    'db',
    'username',
    'client_name',
    'service_name',
    'sentinels',
    'unix_socket_path',
    'path',
    'socket_timeout',
    'socket_connect_timeout',
    'socket_keepalive',
    'health_check_interval',
    'protocol',
    'encoding',
    'decode_responses',
)


def get_displayable_connection_kwargs(queue: Queue) -> dict[str, Any]:
    """Return safe Redis connection metadata for templates and JSON output.

    Only operationally meaningful fields are returned. Secret-bearing values
    and redis-py internals are excluded by the allowlist.

    For Sentinel-backed queues, host and port reflect the first sentinel
    endpoint; sentinels lists all known endpoints; service_name identifies the
    master.
    """
    pool = queue.connection.connection_pool
    connection_kwargs = pool.connection_kwargs.copy()

    if isinstance(pool, SentinelConnectionPool):
        connection_kwargs['service_name'] = getattr(pool, 'service_name', None)
        sentinel_connections = pool.sentinel_manager.sentinels
        sentinel_kwargs = [
            sentinel.connection_pool.connection_kwargs
            for sentinel in sentinel_connections
        ]
        if sentinel_kwargs:
            first_sentinel_kwargs = sentinel_kwargs[0]
            connection_kwargs['host'] = first_sentinel_kwargs.get('host')
            connection_kwargs['port'] = first_sentinel_kwargs.get('port')
            connection_kwargs['sentinels'] = [
                (kwargs.get('host'), kwargs.get('port'))
                for kwargs in sentinel_kwargs
                if kwargs.get('host') is not None and kwargs.get('port') is not None
            ]

    return {
        key: connection_kwargs[key]
        for key in _DISPLAYABLE_CONNECTION_KWARGS
        if connection_kwargs.get(key) is not None
    }


def get_statistics(run_maintenance_tasks: bool = False) -> dict[str, list[dict[str, Any]]]:
    queues = []
    for index, config in enumerate(get_queues_list()):
        queue = get_queue_by_index(index)
        connection = queue.connection

        if run_maintenance_tasks:
            clean_registries(queue)
            clean_worker_registry(queue)

        # Raw access to the first item from left of the redis list.
        # This might not be accurate since new job can be added from the left
        # with `at_front` parameters.
        # Ideally rq should supports Queue.oldest_job
        last_job_id = connection.lindex(queue.key, 0)
        last_job = queue.fetch_job(last_job_id.decode('utf-8')) if last_job_id else None
        if last_job:
            oldest_job_timestamp = to_localtime(last_job.enqueued_at).strftime('%Y-%m-%d, %H:%M:%S')
        else:
            oldest_job_timestamp = "-"

        connection_kwargs = get_displayable_connection_kwargs(queue)

        queue_data = {
            'name': queue.name,
            'jobs': queue.count,
            'oldest_job_timestamp': oldest_job_timestamp,
            'index': index,
            'connection_kwargs': connection_kwargs,
            'scheduler_pid': get_scheduler_pid(queue),
        }

        connection = get_connection(queue.name)
        queue_data['workers'] = Worker.count(queue=queue)

        finished_job_registry = FinishedJobRegistry(queue.name, connection)
        started_job_registry = StartedJobRegistry(queue.name, connection)
        deferred_job_registry = DeferredJobRegistry(queue.name, connection)
        failed_job_registry = FailedJobRegistry(queue.name, connection)
        scheduled_job_registry = ScheduledJobRegistry(queue.name, connection)
        queue_data['finished_jobs'] = len(finished_job_registry)
        queue_data['started_jobs'] = len(started_job_registry)
        queue_data['deferred_jobs'] = len(deferred_job_registry)
        queue_data['failed_jobs'] = len(failed_job_registry)
        queue_data['scheduled_jobs'] = len(scheduled_job_registry)

        queues.append(queue_data)

    return {'queues': queues}


def get_scheduler_statistics() -> dict[str, dict[str, Any]]:
    schedulers = {}
    for index, config in enumerate(get_queues_list()):
        # there is only one scheduler per redis connection, so we use the connection as key
        # to handle the possibility of a configuration with multiple redis connections and scheduled
        # jobs in more than one of them
        queue = get_queue_by_index(index)
        connection_kwargs = get_displayable_connection_kwargs(queue)
        conn_key = (
            f"{connection_kwargs.get('host', 'NOHOST')}:{connection_kwargs.get('port', 6379)}/"
            f"{connection_kwargs.get('db', 0)}"
        )
        if conn_key not in schedulers:
            try:
                scheduler = get_scheduler(config['name'])
                schedulers[conn_key] = {
                    'count': scheduler.count(),
                    'index': index,
                }
            except ImproperlyConfigured:
                pass
    return {'schedulers': schedulers}


def get_cron_schedulers() -> list[DjangoCronScheduler]:
    """
    Fetches all running CronScheduler instances from each unique Redis connection
    defined in RQ_QUEUES.

    Returns:
        List of running DjangoCronScheduler instances
    """
    unique_configs = get_unique_connection_configs()
    cron_schedulers = []

    for config in unique_configs:
        try:
            connection = get_redis_connection(config)
            # Fetch all running schedulers for this connection
            schedulers = DjangoCronScheduler.all(connection, cleanup=True)
            cron_schedulers.extend(schedulers)
        except Exception:
            # Skip configs that fail to create a connection
            # (e.g., USE_REDIS_CACHE without django-redis installed)
            pass

    return cron_schedulers


def get_jobs(
    queue,
    job_ids,
    registry: Optional[
        Union[
            DeferredJobRegistry,
            FailedJobRegistry,
            FinishedJobRegistry,
            ScheduledJobRegistry,
            StartedJobRegistry,
        ]
    ] = None,
) -> list[Job]:
    """Fetch jobs in bulk from Redis.
    1. If job data is not present in Redis, discard the result
    2. If `registry` argument is supplied, delete empty jobs from registry
    """
    jobs = Job.fetch_many(job_ids, connection=queue.connection, serializer=queue.serializer)
    valid_jobs = []
    for i, job in enumerate(jobs):
        if job is None:
            if registry:
                registry.remove(job_ids[i])
        else:
            valid_jobs.append(job)

    return valid_jobs


def get_executions(queue, composite_keys: list[tuple[str, str]]) -> list[Execution]:
    """Fetch executions in bulk from Redis.
    1. If execution data is not present in Redis, discard the result
    """
    executions = []
    for job_id, id in composite_keys:
        try:
            executions.append(Execution.fetch(id=id, job_id=job_id, connection=queue.connection))
        except ValueError:
            pass
    return executions


def stop_jobs(queue: Queue, job_ids: Union[str, list[str], tuple[str, ...]]) -> tuple[list[str], list[str]]:
    job_ids = job_ids if isinstance(job_ids, (list, tuple)) else [job_ids]
    stopped_job_ids = []
    failed_to_stop_job_ids = []
    for job_id in job_ids:
        try:
            send_stop_job_command(queue.connection, job_id)
        except Exception:
            failed_to_stop_job_ids.append(job_id)
            continue
        stopped_job_ids.append(job_id)
    return stopped_job_ids, failed_to_stop_job_ids


def requeue_job(queue: Queue, job: Job) -> None:
    """Re-enqueue a job from any source registry (failed/finished/deferred/scheduled)."""
    status = job.get_status(refresh=False)
    registry: Optional[BaseRegistry] = None
    if status == JobStatus.DEFERRED:
        registry = DeferredJobRegistry(queue.name, queue.connection)
    elif status == JobStatus.FINISHED:
        registry = FinishedJobRegistry(queue.name, queue.connection)
    elif status == JobStatus.SCHEDULED:
        registry = ScheduledJobRegistry(queue.name, queue.connection)
    elif status == JobStatus.FAILED:
        registry = FailedJobRegistry(queue.name, queue.connection)

    with queue.connection.pipeline() as pipeline:
        try:
            # _enqueue_job is new in RQ 1.14, this is used to enqueue
            # job regardless of its dependencies
            queue._enqueue_job(job, pipeline=pipeline)
        except AttributeError:
            queue.enqueue_job(job, pipeline=pipeline)
        if registry is not None:
            registry.remove(job, pipeline=pipeline)
        pipeline.execute()


def reset_db_connections() -> None:
    for c in connections.all():
        c.close()
