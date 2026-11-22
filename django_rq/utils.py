from collections import defaultdict
from typing import Any, Optional, Union

from django.core.exceptions import ImproperlyConfigured
from django.core.paginator import Paginator
from django.db import connections
from django.http import HttpRequest
from redis import Redis
from redis.exceptions import RedisError
from rq.command import send_stop_job_command
from rq.cron import CronScheduler
from rq.executions import Execution
from rq.job import Job, JobStatus
from rq.queue import Queue
from rq.rate_limit import RateLimitRegistry
from rq.registry import (
    BaseRegistry,
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
    clean_registries,
)
from rq.utils import as_text
from rq.worker import Worker
from rq.worker_registration import clean_worker_registry

from .connection_utils import (
    ConnectionType,
    SentinelAddress,
    TCPAddress,
    get_connection,
    get_connection_groups,
    get_connection_identity,
    get_connection_label,
)
from .cron import DjangoCronScheduler
from .queues import RQ_SCHEDULER_INSTALLED, get_queue_by_index, get_scheduler
from .settings import get_queues_list, get_queues_map
from .templatetags.django_rq import to_localtime

DEFAULT_ITEMS_PER_PAGE = 100

# The registry a job waits in, keyed by the status that puts it there.
REGISTRY_BY_STATUS: dict[JobStatus, type[BaseRegistry]] = {
    JobStatus.DEFERRED: DeferredJobRegistry,
    JobStatus.FINISHED: FinishedJobRegistry,
    JobStatus.SCHEDULED: ScheduledJobRegistry,
    JobStatus.FAILED: FailedJobRegistry,
}

REQUEUEABLE_STATUSES = {
    JobStatus.DEFERRED,
    JobStatus.FINISHED,
    JobStatus.SCHEDULED,
    JobStatus.FAILED,
}


def paginate(
    request: HttpRequest, num_items: int, items_per_page: int = DEFAULT_ITEMS_PER_PAGE
) -> tuple[int, list[Union[int, str]], int]:
    """Returns (page, page_range, offset) for a paginated view.

    The page number comes from user input, so it is validated rather than trusted: an
    unparseable or out of range page would otherwise become a negative or oversized Redis
    offset, which silently returns the wrong slice.

    `page_range` is elided around the current page, so a queue holding a million jobs links to
    a dozen pages rather than ten thousand. Gaps are marked with `Paginator.ELLIPSIS`, which
    templates render as plain text via the `is_ellipsis` filter.
    """
    if num_items <= 0:
        return 1, [], 0

    # Paginator only needs a sized sequence to count pages, not the items themselves.
    # `range()` is lazy, so nothing extra is read from Redis.
    paginator = Paginator(range(num_items), items_per_page)

    try:
        # Page numbers below 1 are clamped to the first page. `get_page()` would send them
        # to the *last* page, which is a surprising place to land from `?page=0`.
        number = max(1, int(request.GET.get('page', 1)))
    except (TypeError, ValueError):
        number = 1

    # `get_page()` clamps a page past the end to the last page and never raises.
    page = paginator.get_page(number)
    # Up to 10 pages are listed in full; beyond that the range elides to `1 2 … 8 9 10 … 99 100`
    page_range = list(paginator.get_elided_page_range(page.number))
    return page.number, page_range, items_per_page * (page.number - 1)


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
        return queue.scheduler_pid
    except Exception:
        return None


def get_displayable_connection_kwargs(obj: Union[Queue, CronScheduler]) -> dict[str, Any]:
    """Return the Redis address and database for templates and JSON output."""
    identity = get_connection_identity(obj.connection)
    address = identity.address
    if isinstance(address, TCPAddress):
        return {'host': address.host, 'port': address.port, 'db': identity.db}
    if isinstance(address, SentinelAddress):
        return {'sentinels': list(address.endpoints), 'service_name': address.service_name, 'db': identity.db}
    if identity.connection_type is ConnectionType.UNIX:
        return {'path': address, 'db': identity.db}
    return {}


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


def get_scheduler_statistics() -> dict[str, list[dict[str, Any]]]:
    if not RQ_SCHEDULER_INSTALLED:
        return {'schedulers': []}

    schedulers = []
    queue_index_by_name = get_queues_map()
    for identity, group in get_connection_groups().items():
        connection = group.client()
        name = group.names[0]
        try:
            scheduler = get_scheduler(name, connection=connection)
            schedulers.append(
                {
                    'label': get_connection_label(identity),
                    'count': scheduler.count(),
                    'index': queue_index_by_name[name],
                }
            )
        except ImproperlyConfigured:
            pass
    return {'schedulers': schedulers}


def get_cron_schedulers() -> list[DjangoCronScheduler]:
    """Fetch running cron schedulers once per configured Redis database."""
    cron_schedulers = []
    for index, group in enumerate(get_connection_groups().values()):
        try:
            schedulers = DjangoCronScheduler.all(group.client(), cleanup=True)
        except Exception:
            # Skip connections that fail to initialize or reach the database.
            continue
        for scheduler in schedulers:
            scheduler.connection_index = index
        cron_schedulers.extend(schedulers)
    return cron_schedulers


def _optional_int(value: Any) -> Optional[int]:
    """An integer read from a rate limit pipeline, or None when it is unavailable.

    Redis returns an error in place of a value for a key whose name collides with another
    key's, e.g. a rate limit literally named "reports:allowed"; an unset concurrency reads
    back as None.
    """
    if value is None or isinstance(value, Exception):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_rate_limits(limit: int = 20) -> tuple[list[dict[str, Any]], int]:
    """A preview of the rate limits registered across the Redis databases in RQ_QUEUES.

    Rate limit keys are often per-tenant and unbounded, so this is a preview: the first
    `limit` keys in global alphabetical order -- so one busy database can fill it and hide
    another's keys entirely -- plus the total number found, which lets a caller say how many
    were left out. Every key is read and sorted to make that order deterministic, so
    discovery costs one SMEMBERS per database however small the preview is; only the keys
    that survive the cap cost a round trip for their counts.

    A rate limit key belongs to a database rather than a queue, but the detail view is
    addressed by queue index, so each row carries the index of a queue on its database.
    """
    queues_map = get_queues_map()
    connection_by_index: dict[int, Redis] = {}
    label_by_index: dict[int, str] = {}
    entries: list[tuple[str, int]] = []
    for identity, group in get_connection_groups().items():
        # Any queue on the database will do: the group shares one connection, and the
        # queue's index is what addresses the detail view.
        index = queues_map[group.names[0]]
        try:
            connection = group.client()
            keys = connection.smembers(RateLimitRegistry.rl_keys_key)
        except Exception:
            # Skip databases we cannot reach, so one unusable config does not take the whole
            # dashboard down. Same tradeoff as get_cron_schedulers().
            continue
        connection_by_index[index] = connection
        label_by_index[index] = get_connection_label(identity)
        entries.extend((as_text(key), index) for key in keys)

    total = len(entries)
    entries.sort()

    # Rows are built in the order they are rendered, then grouped so each database's numbers
    # can be read in one batch and filled in place. A row whose numbers cannot be read keeps
    # its None values and renders as an em-dash.
    rate_limits: list[dict[str, Any]] = []
    rows_by_index: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for key, index in entries[:limit]:
        row: dict[str, Any] = {
            'key': key,
            'queue_index': index,
            'slot_holder_count': None,
            'waiting_count': None,
            'concurrency': None,
            'connection_label': label_by_index[index],
        }
        rate_limits.append(row)
        rows_by_index[index].append(row)

    for index, rows in rows_by_index.items():
        connection = connection_by_index[index]
        try:
            with connection.pipeline(transaction=False) as pipeline:
                for row in rows:
                    registry = RateLimitRegistry(row['key'], connection)
                    pipeline.zcard(registry.allowed_key)
                    pipeline.zcard(registry.rate_limited_key)
                    pipeline.hget(registry.config_key, 'concurrency')
                # Command errors come back in place rather than raised, so one unreadable key
                # costs its own row's numbers instead of the whole batch. A connection
                # failure still raises, and leaves this database's rows unfilled.
                results = pipeline.execute(raise_on_error=False)
        except RedisError:
            continue
        for position, row in enumerate(rows):
            slot_holder_count, waiting_count, concurrency = results[position * 3 : position * 3 + 3]
            row['slot_holder_count'] = _optional_int(slot_holder_count)
            row['waiting_count'] = _optional_int(waiting_count)
            row['concurrency'] = _optional_int(concurrency)

    return rate_limits, total


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
    """Re-enqueue a job waiting in one of RQ's registries.

    Dependency checks are deliberately bypassed, since requeueing from the dashboard means
    "run this now".

    Raises:
        ValueError: if the job's status is not requeueable, because it is already queued,
            running or canceled, or if it was requeued concurrently.
    """
    status = job.get_status(refresh=False)
    if status not in REQUEUEABLE_STATUSES:
        # Enqueueing a job that is already queued or running would duplicate it, and a
        # canceled or stopped one would come back from the dead.
        allowed = ', '.join(sorted(requeueable.value for requeueable in REQUEUEABLE_STATUSES))
        raise ValueError(
            f'Cannot requeue job {job.id} with status "{getattr(status, "value", status)}": '
            + f'only {allowed} jobs can be requeued.'
        )

    registry = REGISTRY_BY_STATUS[status](queue.name, queue.connection)

    # The atomic ZREM claims the job, so a repeat or concurrent request cannot requeue it twice.
    if not registry.remove(job):
        raise ValueError(f'Cannot requeue job {job.id}: it was already requeued.')

    # `_enqueue_job` puts the job straight onto the queue, ignoring its dependencies.
    queue._enqueue_job(job)


def reset_db_connections() -> None:
    for c in connections.all():
        c.close()
