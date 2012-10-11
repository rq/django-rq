from django.shortcuts import render

from rq import Worker
from rq.job import Job

from .queues import get_connection, get_connection_by_index, get_queue, get_queue_by_index
from .settings import QUEUES, QUEUES_LIST


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


def jobs(request, queue_index):

    queue = get_queue_by_index(int(queue_index))
    context_data = {
        'queue': queue,
        'queue_index': int(queue_index),
        'jobs': queue.jobs,
    }

    return render(request, 'django_rq/jobs.html', context_data)


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
