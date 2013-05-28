from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render

from rq import requeue_job, Worker
from rq.job import Job

from .queues import get_connection, get_queue_by_index
from .settings import QUEUES_LIST


@staff_member_required
def stats(request):
    queues = []
    for index, config in enumerate(QUEUES_LIST):
        queue = get_queue_by_index(index)
        queue_data = {
            'name': queue.name,
            'jobs': queue.count,
            'index': index,
        }
        if queue.name == 'failed':
            queue_data['workers'] = '-'
        else:
            connection = get_connection(queue.name)
            all_workers = Worker.all(connection=connection)
            queue_workers = [worker for worker in all_workers if queue in worker.queues]
            queue_data['workers'] = len(queue_workers)
        queues.append(queue_data)

    context_data = {'queues': queues}
    return render(request, 'django_rq/stats.html', context_data)


@staff_member_required
def jobs(request, queue_index):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    context_data = {
        'queue': queue,
        'queue_index': queue_index,
        'jobs': queue.jobs,
    }

    return render(request, 'django_rq/jobs.html', context_data)


@staff_member_required
def job_detail(request, queue_index, job_id):
    queue_index = int(queue_index)
    queue = get_queue_by_index(queue_index)
    job = Job.fetch(job_id, connection=queue.connection)
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

    if request.POST:
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
    if request.POST:
        requeue_job(job_id, connection=queue.connection)
        messages.info(request, 'You have successfully requeued %s' % job.id)
        return redirect('rq_job_detail', queue_index, job_id)

    context_data = {
        'queue_index': queue_index,
        'job': job,
        'queue': queue,
    }
    return render(request, 'django_rq/delete_job.html', context_data)
