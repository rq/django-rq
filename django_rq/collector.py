"""
RQ metrics collector.
"""

import logging

import django_rq
from datetime import timedelta
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.core import REGISTRY
from prometheus_client.core import CounterMetricFamily
from rq import Worker
from django.conf import settings
from rq.scheduler import SchedulerStatus
from rq_scheduler.scheduler import Scheduler


logger = logging.getLogger(__name__)


def get_workers_stats(worker_class=None):
    """Get the RQ workers stats.
    Args:
        worker_class (type): RQ Worker class
    Returns:
        list: List of worker stats as a dict {name, queues, state}
    Raises:
        redis.exceptions.RedisError: On Redis connection errors
    """
    worker_class = worker_class if worker_class is not None else Worker

    workers = worker_class.all()

    return [
        {"name": w.name, "queues": w.queue_names(), "state": w.get_state()}
        for w in workers
    ]


class RQCollector(object):
    """RQ stats collector.
    Args:
        connection (redis.Redis): Redis connection instance.
        worker_class (type): RQ Worker class
        queue_class (type): RQ Queue class
    """

    def __init__(self, queues):
        self.queues = queues

        # RQ data collection count and time in seconds
        # self.summary = Summary(
        #     "rq_request_processing_seconds", "Time spent collecting RQ data"
        # )

    def collect(self):
        """Collect RQ Metrics.
        Note:
            This method will be called on registration and every time the metrics are requested.
        Yields:
            RQ metrics for workers and jobs.
        Raises:
            redis.exceptions.RedisError: On Redis connection errors
        """
        logger.debug("Collecting the RQ metrics...")

        yield from self.collect_queue()
        yield from self.collect_worker()
        yield from self.collect_scheduler()

        logger.debug("RQ metrics collection finished")

    def collect_queue(self):
        rq_messages = GaugeMetricFamily(
            "rq_jobs", "RQ messages Count", labels=["queue"]
        )
        rq_registry_count = CounterMetricFamily(
            "rq_registry_count", "RQ Registry Count", labels=["queue", "state"]
        )
        for queue in self.queues:
            rq_messages.add_metric([queue.name], queue.count)

            rq_registry_count.add_metric(
                [queue.name, "deferred"], queue.deferred_job_registry.count
            )
            rq_registry_count.add_metric(
                [queue.name, "failed"], queue.failed_job_registry.count
            )
            rq_registry_count.add_metric(
                [queue.name, "finished"], queue.finished_job_registry.count
            )
            rq_registry_count.add_metric(
                [queue.name, "scheduled"], queue.scheduled_job_registry.count
            )
            rq_registry_count.add_metric(
                [queue.name, "started"], queue.started_job_registry.count
            )
        yield rq_messages
        yield rq_registry_count

    def collect_worker(self):
        rq_workers = GaugeMetricFamily(
            "rq_workers", "RQ workers", labels=["name", "state", "queues"]
        )
        rq_worker_job_count = CounterMetricFamily(
            "rq_worker_job_count",
            "RQ job count per worker",
            labels=["state", "worker_name"],
        )
        rq_worker_total_working_seconds = CounterMetricFamily(
            "rq_worker_workings_seconds_total",
            "RQ worker work seconds total",
            labels=["worker_name"],
        )
        rq_worker_current_working_seconds_gauge = CounterMetricFamily(
            "rq_worker_current_working_seconds_gauge",
            "RQ worker work seconds for current job in seconds",
            labels=["worker_name"],
        )
        checked_workers = set()
        for queue in self.queues:
            queue_workers = Worker.all(queue=queue)
            for worker in queue_workers:
                if worker.name in checked_workers:
                    continue

                rq_workers.add_metric(
                    [
                        worker.name,
                        worker._state,
                        ",".join([q.name for q in worker.queues]),
                    ],
                    1,
                )

                rq_worker_job_count.add_metric(
                    ["successful", worker.name], worker.successful_job_count
                )
                rq_worker_job_count.add_metric(
                    ["failed", worker.name], worker.failed_job_count
                )
                rq_worker_total_working_seconds.add_metric(
                    [worker.name], worker.total_working_time
                )
                rq_worker_current_working_seconds_gauge.add_metric(
                    [worker.name], worker.current_job_working_time
                )
                checked_workers.add(worker.name)

        yield rq_workers
        yield rq_worker_job_count
        yield rq_worker_total_working_seconds
        yield rq_worker_current_working_seconds_gauge

    def collect_scheduler(self):
        checked_schedulers = set()
        rq_scheduler_gauge = GaugeMetricFamily(
            "rq_schedulers", "RQ Schedulers", labels=["scheduler_name", "lock_acquired"]
        )
        jobs_in_hour = GaugeMetricFamily(
            "rq_sheduler_jobs_in_next_hour_gauge", "RQ scheduled jobs in 1 hour"
        )
        for queue in self.queues:
            scheduler = django_rq.get_scheduler()
            list_of_job_instances = scheduler.get_jobs(until=timedelta(hours=1))
            jobs_in_hour.add_metric([], len(list(list_of_job_instances)))

        yield jobs_in_hour


all_queues = [
    django_rq.get_queue(queue_name) for queue_name in settings.RQ_QUEUES.keys()
]
REGISTRY.register(RQCollector(all_queues))
