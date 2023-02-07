from rq.job import Job
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
    clean_registries,
)
from rq.worker import Worker
from rq.worker_registration import clean_worker_registry


from .queues import get_connection, get_queue_by_index, get_scheduler
from .settings import QUEUES_LIST
from .templatetags.django_rq import to_localtime
from django.core.exceptions import ImproperlyConfigured

def scheduler_pid(queue):
    '''Checks whether there's a scheduler-lock on a particular queue, and returns the PID.
        If rq_scheduler is used, return True
    '''
    try:
        print("getting scheduler")
        scheduler = get_scheduler()  # should fail if rq_scheduler not present
        print("got scheduler. getting lock_key")
        lock_key = scheduler.scheduler_lock_key
        print(f"got lock_key {lock_key}. getting value")
        with scheduler.connection.pipeline() as p:
            if _ := p.get(lock_key):
                print(f"got value {_}, returning True")
                return True  # Since no pid info provided, return True
            else:
                for key in p.keys(f"{scheduler.redis_scheduler_namespace_prefix}*"):
                    if not p.hexists(key, 'death'):
                        return True
    except ImproperlyConfigured:
        from rq.scheduler import RQScheduler
        # When a scheduler acquires a lock it adds an expiring key: (e.g: rq:scheduler-lock:<queue.name>)
        # If the key exists
        if pid := queue.connection.get(RQScheduler.get_locking_key(queue.name)):
            return pid
    except Exception as e:
        return str(e)
    return None


def get_statistics(run_maintenance_tasks=False):
    queues = []
    for index, config in enumerate(QUEUES_LIST):
        queue = get_queue_by_index(index)
        connection = queue.connection
        connection_kwargs = connection.connection_pool.connection_kwargs

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

        # parse_class and connection_pool are not needed and not JSON serializable
        connection_kwargs.pop('parser_class', None)
        connection_kwargs.pop('connection_pool', None)

        queue_data = {
            'name': queue.name,
            'jobs': queue.count,
            'oldest_job_timestamp': oldest_job_timestamp,
            'index': index,
            'connection_kwargs': connection_kwargs,
            'scheduler_pid': scheduler_pid(queue),
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


def get_jobs(queue, job_ids, registry=None):
    """Fetch jobs in bulk from Redis.
    1. If job data is not present in Redis, discard the result
    2. If `registry` argument is supplied, delete empty jobs from registry
    """
    jobs = Job.fetch_many(job_ids, connection=queue.connection)
    valid_jobs = []
    for i, job in enumerate(jobs):
        if job is None:
            if registry:
                registry.remove(job_ids[i])
        else:
            valid_jobs.append(job)

    return valid_jobs
