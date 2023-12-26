from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from rq.command import send_stop_job_command
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


def get_scheduler_pid(queue):
    '''Checks whether there's a scheduler-lock on a particular queue, and returns the PID.
        It Only works with RQ's Built-in RQScheduler.
        When RQ-Scheduler is available returns False
        If not, it checks the RQ's RQScheduler for a scheduler lock in the desired queue
        Note: result might have some delay (1-15 minutes) but it helps visualizing whether the setup is working correcly
    '''
    try:
        # first try get the rq-scheduler
        scheduler = get_scheduler(queue.name)  # should fail if rq_scheduler not present
        return False  # Not possible to give useful information without creating a performance issue (redis.keys())
    except ImproperlyConfigured:
        from rq.scheduler import RQScheduler

        # When a scheduler acquires a lock it adds an expiring key: (e.g: rq:scheduler-lock:<queue.name>)
        #TODO: (RQ>= 1.13) return queue.scheduler_pid
        pid = queue.connection.get(RQScheduler.get_locking_key(queue.name))
        return int(pid.decode()) if pid is not None else None
    except Exception as e:
        pass  # Return None
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


def get_scheduler_statistics():
    schedulers = {}
    for index, config in enumerate(QUEUES_LIST):
        # there is only one scheduler per redis connection, so we use the connection as key
        # to handle the possibility of a configuration with multiple redis connections and scheduled
        # jobs in more than one of them
        queue = get_queue_by_index(index)
        connection = queue.connection.connection_pool.connection_kwargs
        conn_key = f"{connection['host']}:{connection.get('port', 6379)}/{connection.get('db', 0)}"
        if conn_key not in schedulers:
            try:
                scheduler = get_scheduler(config['name'])
                schedulers[conn_key] ={
                    'count': scheduler.count(),
                    'index': index,
                }
            except ImproperlyConfigured:
                pass
    return {'schedulers': schedulers}


def get_jobs(queue, job_ids, registry=None):
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


def stop_jobs(queue, job_ids):
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


def reset_db_connections():
    for c in connections.all():
        c.close()


def configure_sentry(sentry_dsn, **options):
    """
    Configure the Sentry client.

    The **options kwargs are passed straight from the command
    invocation - options relevant to Sentry configuration are
    extracted.

    In addition to the 'debug' and 'ca_certs' options, which can
    be passed in as command options, we add the RqIntegration and
    DjangoIntegration to the config.

    Raises ImportError if the sentry_sdk is not available.

    """
    import sentry_sdk
    sentry_options = {
        'debug': options.get('sentry_debug', False),
        'ca_certs': options.get('sentry_ca_certs', None),
        'integrations': [
            sentry_sdk.integrations.redis.RedisIntegration(),
            sentry_sdk.integrations.rq.RqIntegration(),
            sentry_sdk.integrations.django.DjangoIntegration()
        ]
    }
    sentry_sdk.init(sentry_dsn, **sentry_options)
