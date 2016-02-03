from __future__ import division

from math import ceil

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.shortcuts import redirect, render

from redis.exceptions import ResponseError
from rq import requeue_job, Worker
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.registry import (DeferredJobRegistry, FinishedJobRegistry,
                         StartedJobRegistry)

from .queues import get_connection, get_queue_by_index
from .settings import QUEUES_LIST


@staff_member_required
def stats(request):
    queues = []
    for index, config in enumerate(QUEUES_LIST):

        queue = get_queue_by_index(index)
        connection = queue.connection

        queue_data = {
            'name': queue.name,
            'jobs': queue.count,
            'index': index,
            'connection_kwargs': connection.connection_pool.connection_kwargs
        }

        if queue.name == 'failed':
            queue_data['workers'] = '-'
            queue_data['finished_jobs'] = '-'
            queue_data['started_jobs'] = '-'
            queue_data['deferred_jobs'] = '-'

        else:
            connection = get_connection(queue.name)
            all_workers = Worker.all(connection=connection)
            queue_workers = [worker for worker in all_workers if queue in worker.queues]
            queue_data['workers'] = len(queue_workers)

            finished_job_registry = FinishedJobRegistry(queue.name, connection)
            started_job_registry = StartedJobRegistry(queue.name, connection)
            deferred_job_registry = DeferredJobRegistry(queue.name, connection)
            queue_data['finished_jobs'] = len(finished_job_registry)
            queue_data['started_jobs'] = len(started_job_registry)
            queue_data['deferred_jobs'] = len(deferred_job_registry)

        queues.append(queue_data)

    context_data = {'queues': queues}
    return render(request, 'django_rq/stats.html', context_data)


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
        job_ids = registry.get_job_ids(offset, items_per_page)

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
        job_ids = registry.get_job_ids(offset, items_per_page)

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
        job_ids = registry.get_job_ids(offset, items_per_page)

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

    context_data = {
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
    }
    return render(request, 'django_rq/job_detail.html', context_data)


@staff_member_required
def delete_job(request, queue_index, job_id):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    job = Job.fetch(job_id, connection=queue.connection)

    if request.method == 'POST':
        # Remove job id from queue and delete the actual job
        queue.connection._lrem(queue.key, 0, job.id)
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
                    queue.connection._lrem(queue.key, 0, job.id)
                    job.delete()
                messages.info(request, 'You have successfully deleted %s jobs!' % len(job_ids))
            elif request.POST['action'] == 'requeue':
                for job_id in job_ids:
                    requeue_job(job_id, connection=queue.connection)
                messages.info(request, 'You have successfully requeued %d  jobs!' % len(job_ids))

    return redirect('rq_jobs', queue_index)
