from math import ceil
from typing import Any, cast, Tuple

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from redis.exceptions import ResponseError
from rq import requeue_job
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)
from rq.worker import Worker
from rq.worker_registration import clean_worker_registry

from .queues import get_queue_by_index, get_scheduler_by_index
from .settings import QUEUES_MAP
from .utils import get_executions, get_jobs, stop_jobs


@never_cache
@staff_member_required
def jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    items_per_page = 100
    num_jobs = queue.count
    page = int(request.GET.get('page', 1))

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = list(range(1, last_page + 1))
        offset = items_per_page * (page - 1)
        jobs = queue.get_jobs(offset, items_per_page)
    else:
        jobs = []
        page_range = []

    context_data = {
        **admin.site.each_context(request),
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_status': 'Queued',
    }
    return render(request, 'django_rq/jobs.html', context_data)


@never_cache
@staff_member_required
def finished_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = FinishedJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))

    if request.GET.get('desc', '1') == '1':
        sort_direction = 'descending'
    else:
        sort_direction = 'ascending'

    jobs = []

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = list(range(1, last_page + 1))
        offset = items_per_page * (page - 1)
        job_ids = registry.get_job_ids(offset, offset + items_per_page - 1, desc=sort_direction == 'descending')
        jobs = get_jobs(queue, job_ids, registry)

    else:
        page_range = []

    context_data = {
        **admin.site.each_context(request),
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'sort_direction': sort_direction,
    }
    return render(request, 'django_rq/finished_jobs.html', context_data)


@never_cache
@staff_member_required
def failed_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = FailedJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))

    if request.GET.get('desc', '1') == '1':
        sort_direction = 'descending'
    else:
        sort_direction = 'ascending'

    jobs = []

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = list(range(1, last_page + 1))
        offset = items_per_page * (page - 1)
        job_ids = registry.get_job_ids(offset, offset + items_per_page - 1, desc=sort_direction == 'descending')
        jobs = get_jobs(queue, job_ids, registry)

    else:
        page_range = []

    context_data = {
        **admin.site.each_context(request),
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'sort_direction': sort_direction,
    }
    return render(request, 'django_rq/failed_jobs.html', context_data)


@never_cache
@staff_member_required
def scheduled_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = ScheduledJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))
    jobs = []

    if request.GET.get('desc', '1') == '1':
        sort_direction = 'descending'
    else:
        sort_direction = 'ascending'

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = list(range(1, last_page + 1))
        offset = items_per_page * (page - 1)
        job_ids = registry.get_job_ids(offset, offset + items_per_page - 1, desc=sort_direction== 'descending')
        jobs = get_jobs(queue, job_ids, registry)
        for job in jobs:
            job.scheduled_at = registry.get_scheduled_time(job)  # type: ignore[attr-defined]
    else:
        page_range = []

    context_data = {
        **admin.site.each_context(request),
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'sort_direction': sort_direction,
    }
    return render(request, 'django_rq/scheduled_jobs.html', context_data)


@never_cache
@staff_member_required
def started_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = StartedJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))
    jobs = []
    executions = []

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = list(range(1, last_page + 1))
        offset = items_per_page * (page - 1)

        try:
            composite_keys = registry.get_job_and_execution_ids(offset, offset + items_per_page - 1)
        except AttributeError:
            composite_keys = [
                cast(Tuple[str, str], key.split(':'))
                for key in registry.get_job_ids(offset, offset + items_per_page - 1)
            ]

        jobs = get_jobs(queue, [i[0] for i in composite_keys], registry)
        executions = get_executions(queue, composite_keys)

    else:
        page_range = []

    context_data = {
        **admin.site.each_context(request),
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_status': 'Started',
        'executions': executions,
    }
    return render(request, 'django_rq/started_job_registry.html', context_data)


@never_cache
@staff_member_required
def workers(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    clean_worker_registry(queue)
    all_workers = Worker.all(queue.connection)
    workers = [worker for worker in all_workers if queue.name in worker.queue_names()]

    context_data = {
        **admin.site.each_context(request),
        'queue': queue,
        'queue_index': queue_index,
        'workers': workers,
    }
    return render(request, 'django_rq/workers.html', context_data)


@never_cache
@staff_member_required
def worker_details(request, queue_index, key):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    worker = Worker.find_by_key(key, connection=queue.connection)
    assert worker
    # Convert microseconds to milliseconds
    worker.total_working_time = worker.total_working_time / 1000

    queue_names = ', '.join(worker.queue_names())

    context_data = {
        **admin.site.each_context(request),
        'queue': queue,
        'queue_index': queue_index,
        'worker': worker,
        'queue_names': queue_names,
        'job': worker.get_current_job(),
        'total_working_time': worker.total_working_time * 1000,
    }
    return render(request, 'django_rq/worker_details.html', context_data)


@never_cache
@staff_member_required
def deferred_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = DeferredJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))
    jobs = []

    if request.GET.get('desc', '1') == '1':
        sort_direction = 'descending'
    else:
        sort_direction = 'ascending'

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = list(range(1, last_page + 1))
        offset = items_per_page * (page - 1)
        job_ids = registry.get_job_ids(offset, offset + items_per_page - 1, desc=sort_direction == 'descending')
        for job_id in job_ids:
            try:
                jobs.append(Job.fetch(job_id, connection=queue.connection, serializer=queue.serializer))
            except NoSuchJobError:
                pass

    else:
        page_range = []

    context_data = {
        **admin.site.each_context(request),
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_status': 'Deferred',
        'sort_direction': sort_direction,
    }
    return render(request, 'django_rq/deferred_jobs.html', context_data)


@never_cache
@staff_member_required
def job_detail(request, queue_index, job_id):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    try:
        job = Job.fetch(job_id, connection=queue.connection, serializer=queue.serializer)
    except NoSuchJobError:
        raise Http404("Couldn't find job with this ID: %s" % job_id)

    try:
        job.func_name
        data_is_valid = True
    except:
        data_is_valid = False

    # Backward compatibility support for RQ < 1.12.0
    rv = job.connection.hget(job.key, 'result')
    if rv is not None:
        # cache the result
        job.legacy_result = job.serializer.loads(rv)  # type: ignore[attr-defined]
    try:
        exc_info = job._exc_info
    except AttributeError:
        exc_info = None

    dependencies = []
    # if job._dependency_ids:
        # Fetch dependencies if they exist
        # dependencies = Job.fetch_many(
        #     job._dependency_ids, connection=queue.connection, serializer=queue.serializer
        # )
    for dependency_id in job._dependency_ids:
        try:
            dependency = Job.fetch(dependency_id, connection=queue.connection, serializer=queue.serializer)
        except NoSuchJobError:
            dependency = None
        dependencies.append((dependency_id, dependency))

    context_data = {
        **admin.site.each_context(request),
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
        'data_is_valid': data_is_valid,
        'exc_info': exc_info,
        'dependencies': dependencies,
    }
    return render(request, 'django_rq/job_detail.html', context_data)


@never_cache
@staff_member_required
def delete_job(request, queue_index, job_id):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    job = Job.fetch(job_id, connection=queue.connection, serializer=queue.serializer)

    if request.method == 'POST':
        # Remove job id from queue and delete the actual job
        queue.connection.lrem(queue.key, 0, job.id)
        job.delete()
        messages.info(request, 'You have successfully deleted %s' % job.id)
        return redirect('rq_jobs', queue_index)

    context_data = {
        **admin.site.each_context(request),
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
    }
    return render(request, 'django_rq/delete_job.html', context_data)


@never_cache
@staff_member_required
def requeue_job_view(request, queue_index, job_id):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    job = Job.fetch(job_id, connection=queue.connection, serializer=queue.serializer)

    if request.method == 'POST':
        requeue_job(job_id, connection=queue.connection, serializer=queue.serializer)
        messages.info(request, 'You have successfully requeued %s' % job.id)
        return redirect('rq_job_detail', queue_index, job_id)

    context_data = {
        **admin.site.each_context(request),
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
    }
    return render(request, 'django_rq/delete_job.html', context_data)


@never_cache
@staff_member_required
def clear_queue(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    if request.method == 'POST':
        try:
            queue.empty()
            messages.info(request, 'You have successfully cleared the queue %s' % queue.name)
        except ResponseError as e:
            try:
                suppress = 'EVALSHA' in e.message  # type: ignore[attr-defined]
            except AttributeError:
                suppress = 'EVALSHA' in str(e)

            if suppress:
                messages.error(
                    request,
                    'This action is not supported on Redis versions < 2.6.0, please use the bulk delete command instead',
                )
            else:
                raise e
        return redirect('rq_jobs', queue_index)

    context_data = {
        **admin.site.each_context(request),
        'queue_index': queue_index,
        'queue': queue,
    }
    return render(request, 'django_rq/clear_queue.html', context_data)


@never_cache
@staff_member_required
def requeue_all(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    registry = FailedJobRegistry(queue=queue)

    if request.method == 'POST':
        job_ids = registry.get_job_ids()
        count = 0
        # Confirmation received
        for job_id in job_ids:
            try:
                requeue_job(job_id, connection=queue.connection, serializer=queue.serializer)
                count += 1
            except NoSuchJobError:
                pass

        messages.info(request, 'You have successfully requeued %d jobs!' % count)
        return redirect('rq_jobs', queue_index)

    context_data = {
        **admin.site.each_context(request),
        'queue_index': queue_index,
        'queue': queue,
        'total_jobs': len(registry),
    }

    return render(request, 'django_rq/requeue_all.html', context_data)


@never_cache
@staff_member_required
def delete_failed_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    registry = FailedJobRegistry(queue=queue)

    if request.method == 'POST':
        job_ids = registry.get_job_ids()
        jobs = Job.fetch_many(job_ids, connection=queue.connection)
        count = 0
        for job in jobs:
            if job:
                job.delete()
                count += 1

        messages.info(request, 'You have successfully deleted %d jobs!' % count)
        return redirect('rq_home')

    context_data = {
        **admin.site.each_context(request),
        'queue_index': queue_index,
        'queue': queue,
        'total_jobs': len(registry),
    }

    return render(request, 'django_rq/clear_failed_queue.html', context_data)


@never_cache
@staff_member_required
def confirm_action(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    next_url = request.META.get('HTTP_REFERER') or reverse('rq_jobs', args=[queue_index])

    if request.method == 'POST' and request.POST.get('action', False):
        # confirm action
        if request.POST.get('_selected_action', False):
            context_data = {
                **admin.site.each_context(request),
                'queue_index': queue_index,
                'action': request.POST['action'],
                'job_ids': request.POST.getlist('_selected_action'),
                'queue': queue,
                'next_url': next_url,
            }
            return render(request, 'django_rq/confirm_action.html', context_data)

    return redirect(next_url)


@never_cache
@staff_member_required
def actions(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    next_url = request.POST.get('next_url') or reverse('rq_jobs', args=[queue_index])

    if request.method == 'POST' and request.POST.get('action', False):
        # do confirmed action
        if request.POST.get('job_ids', False):
            job_ids = request.POST.getlist('job_ids')

            if request.POST['action'] == 'delete':
                for job_id in job_ids:
                    job = Job.fetch(job_id, connection=queue.connection, serializer=queue.serializer)
                    # Remove job id from queue and delete the actual job
                    queue.connection.lrem(queue.key, 0, job.id)
                    job.delete()
                messages.info(request, 'You have successfully deleted %s jobs!' % len(job_ids))
            elif request.POST['action'] == 'requeue':
                for job_id in job_ids:
                    requeue_job(job_id, connection=queue.connection, serializer=queue.serializer)
                messages.info(request, 'You have successfully requeued %d  jobs!' % len(job_ids))
            elif request.POST['action'] == 'stop':
                stopped, failed_to_stop = stop_jobs(queue, job_ids)
                if len(stopped) > 0:
                    messages.info(request, 'You have successfully stopped %d jobs!' % len(stopped))
                if len(failed_to_stop) > 0:
                    messages.error(request, '%d jobs failed to stop!' % len(failed_to_stop))

    return redirect(next_url)


@never_cache
@staff_member_required
def enqueue_job(request, queue_index, job_id):
    """Enqueue deferred jobs"""
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    job = Job.fetch(job_id, connection=queue.connection, serializer=queue.serializer)

    if request.method == 'POST':
        try:
            # _enqueue_job is new in RQ 1.14, this is used to enqueue
            # job regardless of its dependencies
            queue._enqueue_job(job)
        except AttributeError:
            queue.enqueue_job(job)

        # Remove job from correct registry if needed
        registry: Any
        if job.get_status() == JobStatus.DEFERRED:
            registry = DeferredJobRegistry(queue.name, queue.connection)
            registry.remove(job)
        elif job.get_status() == JobStatus.FINISHED:
            registry = FinishedJobRegistry(queue.name, queue.connection)
            registry.remove(job)
        elif job.get_status() == JobStatus.SCHEDULED:
            registry = ScheduledJobRegistry(queue.name, queue.connection)
            registry.remove(job)

        messages.info(request, 'You have successfully enqueued %s' % job.id)
        return redirect('rq_job_detail', queue_index, job_id)

    context_data = {
        **admin.site.each_context(request),
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
    }
    return render(request, 'django_rq/delete_job.html', context_data)


@never_cache
@staff_member_required
@require_POST
def stop_job(request, queue_index, job_id):
    """Stop started job"""
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    stopped, _ = stop_jobs(queue, job_id)
    if len(stopped) == 1:
        messages.info(request, 'You have successfully stopped %s' % job_id)
        return redirect('rq_job_detail', queue_index, job_id)
    else:
        messages.error(request, 'Failed to stop %s' % job_id)
        return redirect('rq_job_detail', queue_index, job_id)


@never_cache
@staff_member_required
def scheduler_jobs(request, scheduler_index):
    scheduler = get_scheduler_by_index(scheduler_index)

    items_per_page = 100
    num_jobs = scheduler.count()
    page = int(request.GET.get('page', 1))
    jobs = []

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = list(range(1, last_page + 1))
        offset = items_per_page * (page - 1)
        jobs_times = scheduler.get_jobs(with_times=True, offset=offset, length=items_per_page)
        for job, time in jobs_times:
            job.next_run = time
            job.queue_index = QUEUES_MAP.get(job.origin, 0)
            if 'cron_string' in job.meta:
                job.schedule = f"cron: '{job.meta['cron_string']}'"
            elif 'interval' in job.meta:
                job.schedule = f"interval: {job.meta['interval']}"
                if 'repeat' in job.meta:
                    job.schedule += f" repeat: {job.meta['repeat']}"
            else:
                job.schedule = 'unknown'
            jobs.append(job)
    else:
        page_range = []

    context_data = {
        **admin.site.each_context(request),
        'scheduler': scheduler,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
    }
    return render(request, 'django_rq/scheduler.html', context_data)
