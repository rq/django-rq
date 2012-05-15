from django.shortcuts import render

from rq import Worker

from .queues import get_connection, get_queue
from .settings import QUEUES


def stats(request):
    queues = []
    for name in QUEUES:
        queue = get_queue(name)
        connection = get_connection(name)
        all_workers = Worker.all(connection=connection)
        queue_workers = [worker for worker in all_workers if queue in worker.queues]
        stat = {
            'name': name,
            'jobs': queue.count,
            'workers': len(queue_workers)
        }
        queues.append(stat)
    context_data = { 'queues': queues }
    return render(request, 'django_rq/stats.html', context_data)