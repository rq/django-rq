from rq.job import JobStatus

from .queues import filter_connection_params, get_connection, get_queue, get_unique_connection_configs
from .workers import get_worker_class

try:
    from prometheus_client import Summary
    from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

    class RQCollector:
        """RQ stats collector"""

        summary = Summary('rq_request_processing_seconds', 'Time spent collecting RQ data')

        def collect(self):
            from .settings import QUEUES

            with self.summary.time():
                rq_workers = GaugeMetricFamily('rq_workers', 'RQ workers', labels=['name', 'state', 'queues'])
                rq_workers_success = CounterMetricFamily('rq_workers_success', 'RQ workers success count', labels=['name', 'queues'])
                rq_workers_failed = CounterMetricFamily('rq_workers_failed', 'RQ workers fail count', labels=['name', 'queues'])
                rq_workers_working_time = CounterMetricFamily('rq_workers_working_time', 'RQ workers spent seconds', labels=['name', 'queues'])

                rq_jobs = GaugeMetricFamily('rq_jobs', 'RQ jobs by state', labels=['queue', 'status'])

                worker_class = get_worker_class()
                unique_configs = get_unique_connection_configs()
                connections = {}
                for queue_name, config in QUEUES.items():
                    index = unique_configs.index(filter_connection_params(config))
                    if index not in connections:
                        connections[index] = connection = get_connection(queue_name)

                        for worker in worker_class.all(connection):
                            name = worker.name
                            label_queues = ','.join(worker.queue_names())
                            rq_workers.add_metric([name, worker.get_state(), label_queues], 1)
                            rq_workers_success.add_metric([name, label_queues], worker.successful_job_count)
                            rq_workers_failed.add_metric([name, label_queues], worker.failed_job_count)
                            rq_workers_working_time.add_metric([name, label_queues], worker.total_working_time)
                    else:
                        connection = connections[index]

                    queue = get_queue(queue_name, connection=connection)
                    rq_jobs.add_metric([queue_name, JobStatus.QUEUED], queue.count)
                    rq_jobs.add_metric([queue_name, JobStatus.STARTED], queue.started_job_registry.count)
                    rq_jobs.add_metric([queue_name, JobStatus.FINISHED], queue.finished_job_registry.count)
                    rq_jobs.add_metric([queue_name, JobStatus.FAILED], queue.failed_job_registry.count)
                    rq_jobs.add_metric([queue_name, JobStatus.DEFERRED], queue.deferred_job_registry.count)
                    rq_jobs.add_metric([queue_name, JobStatus.SCHEDULED], queue.scheduled_job_registry.count)

                yield rq_workers
                yield rq_workers_success
                yield rq_workers_failed
                yield rq_workers_working_time
                yield rq_jobs

except ImportError:
    RQCollector = None
