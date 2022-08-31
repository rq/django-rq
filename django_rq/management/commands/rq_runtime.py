import django_rq

from django.core.management.base import CommandParser
from django.core.management.base import BaseCommand
from rq.registry import FinishedJobRegistry
from django_rq.utils import get_jobs

import logging
from tqdm import tqdm
import datetime


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Get queue finished job runtime statistics"

    def add_arguments(self, parser: CommandParser):
        parser.add_argument('--queue',
                            type=str,
                            required=False,
                            default="default",
                            help="Queue name")

    def handle(self, *args, **options):
        queue = options['queue']
        q = django_rq.get_queue(queue)
        registry = FinishedJobRegistry(q.name, q.connection)
        count = len(registry)
        status_runtime_map = {}  # {status: {count: int, sum: float}}
        func_runtime_map = {}  # {status: {count: int, sum: float}}
        step = 1000
        for i in tqdm(range(0, count+1, step)):
            job_ids = registry.get_job_ids(i, step)
            jobs = get_jobs(q, job_ids, registry)
            for job in jobs:
                status = job.get_status(True)
                if status not in status_runtime_map:
                    status_runtime_map[status] = {"count": 0, "sum": 0.0}

                func = job.func_name
                if func not in func_runtime_map:
                    func_runtime_map[func] = {"count": 0, "sum": 0.0}

                status_runtime_map[status]['count'] += 1
                if job.ended_at:
                    runtime = (job.ended_at - job.enqueued_at).total_seconds()
                else:
                    runtime = (datetime.datetime.now() - job.enqueued_at).total_seconds()
                status_runtime_map[status]['sum'] += runtime

                func_runtime_map[func]['count'] += 1
                func_runtime_map[func]['sum'] += runtime

        print(f"Total job {count}")
        print("------")
        print("Status\tCount\tAvgRuntime")
        for status in sorted(list(status_runtime_map.keys())):
            item = status_runtime_map[status]
            avg_runtime = item['sum'] / item['count'] if item['count'] > 0 else 0.0
            print(f"{status}\t{item['count']}\t{avg_runtime:4f}s")
        print("------")

        print("Func\tCount\tAvgRuntime")
        for func in sorted(list(func_runtime_map.keys())):
            item = func_runtime_map[func]
            avg_runtime = item['sum'] / item['count'] if item['count'] > 0 else 0.0
            print(f"{func}\t{item['count']}\t{avg_runtime:4f}s")
