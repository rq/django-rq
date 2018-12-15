from rq.registry import (DeferredJobRegistry, FinishedJobRegistry,
                         StartedJobRegistry)
from rq.worker import Worker

from .queues import get_connection, get_queue_by_index
from .settings import QUEUES_LIST
from .templatetags.django_rq import to_localtime


def get_statistics():
    queues = []
    for index, config in enumerate(QUEUES_LIST):

        queue = get_queue_by_index(index)
        connection = queue.connection
        connection_kwargs = connection.connection_pool.connection_kwargs

        # Raw access to the first item from left of the redis list.
        # This might not be accurate since new job can be added from the left
        # with `at_front` parameters.
        # Ideally rq should supports Queue.oldest_job
        last_job_id = connection.lindex(queue.key, 0)
        last_job = queue.fetch_job(last_job_id.decode('utf-8')) if last_job_id else None
        if last_job:
            oldest_job_timestamp = to_localtime(last_job.enqueued_at)\
                .strftime('%Y-%m-%d, %H:%M:%S')
        else:
            oldest_job_timestamp = "-"

        # parse_class and connection_pool are not needed and not JSON serializable
        connection_kwargs.pop('parser_class', None)
        connection_kwargs.pop('connection_pool', None)

        queue_data = {
            'name': queue.name,
            'jobs': queue.count,
            'oldest_job_timestamp': oldest_job_timestamp,
            'index': index,
            'connection_kwargs': connection_kwargs
        }

        if queue.name == 'failed':
            queue_data['workers'] = '-'
            queue_data['finished_jobs'] = '-'
            queue_data['started_jobs'] = '-'
            queue_data['deferred_jobs'] = '-'

        else:
            connection = get_connection(queue.name)
            queue_data['workers'] = Worker.count(queue=queue)

            finished_job_registry = FinishedJobRegistry(queue.name, connection)
            started_job_registry = StartedJobRegistry(queue.name, connection)
            deferred_job_registry = DeferredJobRegistry(queue.name, connection)
            queue_data['finished_jobs'] = len(finished_job_registry)
            queue_data['started_jobs'] = len(started_job_registry)
            queue_data['deferred_jobs'] = len(deferred_job_registry)

        queues.append(queue_data)
    return {'queues': queues}
