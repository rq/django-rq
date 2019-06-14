from __future__ import division

from math import ceil

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from redis.exceptions import ResponseError
from rq import requeue_job
from rq.exceptions import NoSuchJobError, UnpickleError
from rq.job import Job, JobStatus
from rq.registry import (DeferredJobRegistry, FailedJobRegistry,
                         FinishedJobRegistry, StartedJobRegistry)
from rq.worker import Worker

from .queues import get_queue_by_index
from .settings import API_TOKEN
from .utils import get_statistics


@staff_member_required
def stats(request):
    return render(request, 'django_rq/stats.html',
                  get_statistics(run_maintenance_tasks=True))


def stats_json(request, token=None):
    if request.user.is_staff or (token and token == API_TOKEN):
        return JsonResponse(get_statistics())

    return JsonResponse({
        "error": True,
        "description": "Please configure API_TOKEN in settings.py before accessing this view."
    })


@staff_member_required
def jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    items_per_page = 100
    num_jobs = queue.count
    page = int(request.GET.get('page', 1))

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = range(1, last_page + 1)
        offset = items_per_page * (page - 1)
        jobs = queue.get_jobs(offset, items_per_page)
    else:
        jobs = []
        page_range = []

    context_data = {
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_status': 'Queued',
    }
    return render(request, 'django_rq/jobs.html', context_data)


@staff_member_required
def finished_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = FinishedJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))
    jobs = []

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = range(1, last_page + 1)
        offset = items_per_page * (page - 1)
        job_ids = registry.get_job_ids(offset, offset + items_per_page - 1)

        for job_id in job_ids:
            try:
                jobs.append(Job.fetch(job_id, connection=queue.connection))
            except NoSuchJobError:
                pass

    else:
        page_range = []

    context_data = {
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_status': 'Finished',
    }
    return render(request, 'django_rq/jobs.html', context_data)


@staff_member_required
def failed_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = FailedJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))
    jobs = []

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = range(1, last_page + 1)
        offset = items_per_page * (page - 1)
        job_ids = registry.get_job_ids(offset, offset + items_per_page - 1)

        for job_id in job_ids:
            try:
                jobs.append(Job.fetch(job_id, connection=queue.connection))
            except NoSuchJobError:
                pass

    else:
        page_range = []

    context_data = {
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_status': 'Failed',
    }
    return render(request, 'django_rq/jobs.html', context_data)


@staff_member_required
def started_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = StartedJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))
    jobs = []

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = range(1, last_page + 1)
        offset = items_per_page * (page - 1)
        job_ids = registry.get_job_ids(offset, offset + items_per_page - 1)

        for job_id in job_ids:
            try:
                jobs.append(Job.fetch(job_id, connection=queue.connection))
            except NoSuchJobError:
                pass

    else:
        page_range = []

    context_data = {
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_status': 'Started',
    }
    return render(request, 'django_rq/jobs.html', context_data)


@staff_member_required
def workers(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    all_workers = Worker.all(queue.connection)
    workers = [worker for worker in all_workers
               if queue.name in worker.queue_names()]

    context_data = {
        'queue': queue,
        'queue_index': queue_index,
        'workers': workers,
    }
    return render(request, 'django_rq/workers.html', context_data)


@staff_member_required
def worker_details(request, queue_index, key):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    worker = Worker.find_by_key(key, connection=queue.connection)
    # Convert microseconds to milliseconds
    worker.total_working_time = worker.total_working_time / 1000

    queue_names = ', '.join(worker.queue_names())

    context_data = {
        'queue': queue,
        'queue_index': queue_index,
        'worker': worker,
        'queue_names': queue_names,
        'job': worker.get_current_job(),
        'total_working_time': worker.total_working_time * 1000
    }
    return render(request, 'django_rq/worker_details.html', context_data)


@staff_member_required
def deferred_jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    registry = DeferredJobRegistry(queue.name, queue.connection)

    items_per_page = 100
    num_jobs = len(registry)
    page = int(request.GET.get('page', 1))
    jobs = []

    if num_jobs > 0:
        last_page = int(ceil(num_jobs / items_per_page))
        page_range = range(1, last_page + 1)
        offset = items_per_page * (page - 1)
        job_ids = registry.get_job_ids(offset, offset + items_per_page - 1)

        for job_id in job_ids:
            try:
                jobs.append(Job.fetch(job_id, connection=queue.connection))
            except NoSuchJobError:
                pass

    else:
        page_range = []

    context_data = {
        'queue': queue,
        'queue_index': queue_index,
        'jobs': jobs,
        'num_jobs': num_jobs,
        'page': page,
        'page_range': page_range,
        'job_status': 'Deferred',
    }
    return render(request, 'django_rq/jobs.html', context_data)


@staff_member_required
def job_detail(request, queue_index, job_id):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    try:
        job = Job.fetch(job_id, connection=queue.connection)
    except NoSuchJobError:
        raise Http404("Couldn't find job with this ID: %s" % job_id)

    try:
        job.func_name
        data_is_valid = True
    except UnpickleError:
        data_is_valid = False

    context_data = {
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
        'data_is_valid': data_is_valid
    }
    return render(request, 'django_rq/job_detail.html', context_data)


@staff_member_required
def delete_job(request, queue_index, job_id):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    job = Job.fetch(job_id, connection=queue.connection)

    if request.method == 'POST':
        # Remove job id from queue and delete the actual job
        queue.connection.lrem(queue.key, 0, job.id)
        job.delete()
        messages.info(request, 'You have successfully deleted %s' % job.id)
        return redirect('rq_jobs', queue_index)

    context_data = {
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
    }
    return render(request, 'django_rq/delete_job.html', context_data)


@staff_member_required
def requeue_job_view(request, queue_index, job_id):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    job = Job.fetch(job_id, connection=queue.connection)

    if request.method == 'POST':
        requeue_job(job_id, connection=queue.connection)
        messages.info(request, 'You have successfully requeued %s' % job.id)
        return redirect('rq_job_detail', queue_index, job_id)

    context_data = {
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
    }
    return render(request, 'django_rq/delete_job.html', context_data)


@staff_member_required
def clear_queue(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    if request.method == 'POST':
        try:
            queue.empty()
            messages.info(request, 'You have successfully cleared the queue %s' % queue.name)
        except ResponseError as e:
            if 'EVALSHA' in e.message:
                messages.error(request, 'This action is not supported on Redis versions < 2.6.0, please use the bulk delete command instead')
            else:
                raise e
        return redirect('rq_jobs', queue_index)

    context_data = {
        'queue_index': queue_index,
        'queue': queue,
    }
    return render(request, 'django_rq/clear_queue.html', context_data)


@staff_member_required
def requeue_all(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    registry = FailedJobRegistry(queue=queue)

    if request.method == 'POST':
        job_ids = registry.get_job_ids()

        # Confirmation received
        for job_id in job_ids:
            requeue_job(job_id, connection=queue.connection)

        messages.info(request, 'You have successfully requeued all %d jobs!' % len(job_ids))
        return redirect('rq_jobs', queue_index)

    context_data = {
        'queue_index': queue_index,
        'queue': queue,
        'total_jobs': len(registry),
    }

    return render(request, 'django_rq/requeue_all.html', context_data)


@staff_member_required
def actions(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)

    if request.method == 'POST' and request.POST.get('action', False):
        # confirm action
        if request.POST.get('_selected_action', False):
            context_data = {
                'queue_index': queue_index,
                'action': request.POST['action'],
                'job_ids': request.POST.getlist('_selected_action'),
                'queue': queue,
            }
            return render(request, 'django_rq/confirm_action.html', context_data)

        # do confirmed action
        elif request.POST.get('job_ids', False):
            job_ids = request.POST.getlist('job_ids')

            if request.POST['action'] == 'delete':
                for job_id in job_ids:
                    job = Job.fetch(job_id, connection=queue.connection)
                    # Remove job id from queue and delete the actual job
                    queue.connection.lrem(queue.key, 0, job.id)
                    job.delete()
                messages.info(request, 'You have successfully deleted %s jobs!' % len(job_ids))
            elif request.POST['action'] == 'requeue':
                for job_id in job_ids:
                    requeue_job(job_id, connection=queue.connection)
                messages.info(request, 'You have successfully requeued %d  jobs!' % len(job_ids))

    return redirect('rq_jobs', queue_index)


@staff_member_required
def enqueue_job(request, queue_index, job_id):
    """ Enqueue deferred jobs
    """
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    job = Job.fetch(job_id, connection=queue.connection)

    if request.method == 'POST':
        queue.enqueue_job(job)

        # Remove job from correct registry if needed
        if job.get_status() == JobStatus.DEFERRED:
            registry = DeferredJobRegistry(queue.name, queue.connection)
            registry.remove(job)
        elif job.get_status() == JobStatus.FINISHED:
            registry = FinishedJobRegistry(queue.name, queue.connection)
            registry.remove(job)

        messages.info(request, 'You have successfully enqueued %s' % job.id)
        return redirect('rq_job_detail', queue_index, job_id)

    context_data = {
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
    }
    return render(request, 'django_rq/delete_job.html', context_data)
