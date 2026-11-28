from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from rq.job import Job

from .connection_utils import get_connection_by_index
from .cron import (
    CRON_JOB_HISTORY_SUPPORTED,
    DjangoCronScheduler,
    get_cron_job_data,
    get_cron_job_history,
    get_cron_job_history_count,
)
from .queues import get_queue_by_index
from .utils import get_displayable_connection_kwargs, paginate
from .views import each_context

ITEMS_PER_PAGE = 20


def get_scheduler(connection_index: int, scheduler_name: str) -> DjangoCronScheduler:
    """
    Returns the cron scheduler with the given name on the given connection.

    Raises:
        Http404: If the connection index is invalid or the scheduler is not found
    """
    try:
        connection = get_connection_by_index(connection_index)
    except (IndexError, ValueError):
        raise Http404("Invalid connection index")

    for scheduler in DjangoCronScheduler.all(connection, cleanup=True):
        if scheduler.name == scheduler_name:
            return scheduler

    raise Http404(f"Scheduler '{scheduler_name}' not found")


@never_cache
@staff_member_required
def cron_scheduler_detail(request: HttpRequest, connection_index: int, scheduler_name: str) -> HttpResponse:
    """
    Display details for a specific cron scheduler.

    Args:
        request: Django request object
        connection_index: Index of the Redis connection
        scheduler_name: Name of the cron scheduler

    Raises:
        Http404: If the scheduler is not found
    """
    scheduler = get_scheduler(connection_index, scheduler_name)

    context_data = {
        **each_context(request),
        "scheduler": scheduler,
        "connection_index": connection_index,
        "connection_kwargs": get_displayable_connection_kwargs(scheduler),
        "cron_jobs": scheduler.get_jobs_data(),
        "job_history_supported": CRON_JOB_HISTORY_SUPPORTED,
    }

    return render(request, 'django_rq/cron_scheduler_detail.html', context_data)


@never_cache
@staff_member_required
def cron_job_detail(
    request: HttpRequest, connection_index: int, scheduler_name: str, cron_job_name: str
) -> HttpResponse:
    """
    Display a cron job along with the jobs it has spawned.

    Args:
        request: Django request object
        connection_index: Index of the Redis connection
        scheduler_name: Name of the cron scheduler
        cron_job_name: Name of the cron job, which defaults to the function's import path

    Raises:
        Http404: If the scheduler or the cron job is not found
    """
    scheduler = get_scheduler(connection_index, scheduler_name)

    cron_job = None
    for job in scheduler.get_jobs():
        if (getattr(job, 'name', None) or job.func_name) == cron_job_name:
            cron_job = job
            break

    if cron_job is None:
        raise Http404(f"Cron job '{cron_job_name}' not found in scheduler '{scheduler_name}'")

    cron_job_data = get_cron_job_data(cron_job)
    queue_index = cron_job_data['queue_index']

    # Jobs are fetched with their queue's serializer. When the queue is no longer in RQ_QUEUES
    # we can still list the history, using the scheduler's connection and the default serializer.
    if queue_index is not None:
        queue = get_queue_by_index(queue_index)
        connection, serializer = queue.connection, queue.serializer
    else:
        connection, serializer = scheduler.connection, None

    num_jobs = get_cron_job_history_count(cron_job, scheduler.connection)
    page, page_range, offset = paginate(request, num_jobs, ITEMS_PER_PAGE)

    history: list[dict[str, Any]] = []

    if num_jobs > 0:
        entries = get_cron_job_history(cron_job, scheduler.connection, offset, offset + ITEMS_PER_PAGE - 1)

        # A job's data is deleted when its result_ttl expires, long before its history entry
        # goes away, so a missing job is the norm rather than an error. Keep the row and show
        # what the history itself knows: the job's ID and when it was enqueued.
        jobs = Job.fetch_many([job_id for job_id, _ in entries], connection=connection, serializer=serializer)
        history = [
            {'job_id': job_id, 'enqueued_at': enqueued_at, 'job': job}
            for (job_id, enqueued_at), job in zip(entries, jobs)
        ]

    context_data = {
        **each_context(request),
        'scheduler': scheduler,
        'connection_index': connection_index,
        'cron_job': cron_job_data,
        'queue_index': queue_index,
        'history': history,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_history_supported': CRON_JOB_HISTORY_SUPPORTED,
    }

    return render(request, 'django_rq/cron_job_detail.html', context_data)
