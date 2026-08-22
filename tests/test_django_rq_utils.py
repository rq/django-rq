import datetime
from unittest import TestCase
from uuid import uuid4

from django.core.paginator import Paginator
from django.test import RequestFactory, override_settings
from rq.job import JobStatus
from rq.registry import DeferredJobRegistry, FailedJobRegistry, FinishedJobRegistry, ScheduledJobRegistry

from django_rq.cron import DjangoCronScheduler
from django_rq.queues import get_queue
from django_rq.utils import get_cron_schedulers, get_jobs, get_statistics, paginate, requeue_job
from django_rq.workers import get_worker
from tests.fixtures import access_self, failing_job
from tests.redis_config import REDIS_CONFIG_1
from tests.utils import flush_registry


class UtilsTest(TestCase):
    def test_paginate(self):
        """Page numbers come from user input, so unusable ones must not become bad offsets."""
        factory = RequestFactory()

        def paginate_query(page):
            return paginate(factory.get('/', {'page': page}), 250, items_per_page=100)

        # 250 items span 3 pages
        self.assertEqual(paginate_query('2'), (2, [1, 2, 3], 100))

        # Anything unparseable, or below the first page, falls back to the first page
        for page in ('abc', '', '1.5', '0', '-1', '-100'):
            self.assertEqual(paginate_query(page), (1, [1, 2, 3], 0))

        # A page past the end, including one too large for a Redis index, is the last page
        for page in ('4', '99', '9' * 30):
            self.assertEqual(paginate_query(page), (3, [1, 2, 3], 200))

        # No page argument at all, and an empty list, which has no pages to link to
        self.assertEqual(paginate(factory.get('/'), 250, items_per_page=100), (1, [1, 2, 3], 0))
        self.assertEqual(paginate(factory.get('/', {'page': '3'}), 0), (1, [], 0))

        # A long range is elided around the current page instead of linking to all 100 pages
        page, page_range, offset = paginate(factory.get('/', {'page': '50'}), 10000, items_per_page=100)
        self.assertEqual((page, offset), (50, 4900))
        self.assertEqual(page_range[:3], [1, 2, Paginator.ELLIPSIS])
        self.assertEqual(page_range[-3:], [Paginator.ELLIPSIS, 99, 100])
        self.assertIn(50, page_range)
        self.assertLess(len(page_range), 20)

    def test_get_cron_schedulers(self):
        """Test get_cron_schedulers returns running DjangoCronScheduler instances."""
        from django_rq.queues import get_connection

        # Initially, no schedulers should be running
        schedulers = get_cron_schedulers()
        self.assertIsInstance(schedulers, list)
        initial_count = len(schedulers)

        # Start a test scheduler
        connection = get_connection('default')
        test_scheduler = DjangoCronScheduler(connection=connection)
        test_scheduler.register_birth()
        test_scheduler.heartbeat()

        try:
            # Now we should get at least one more scheduler
            schedulers = get_cron_schedulers()
            self.assertGreater(len(schedulers), initial_count)

            # Find our test scheduler in the results
            found_scheduler = None
            for scheduler in schedulers:
                self.assertIsInstance(scheduler, DjangoCronScheduler)
                self.assertIsNotNone(scheduler.connection)
                if scheduler.name == test_scheduler.name:
                    found_scheduler = scheduler

            # Verify our test scheduler was found and has proper data
            assert found_scheduler is not None  # Type narrowing for mypy
            self.assertIsNotNone(found_scheduler.last_heartbeat)

        finally:
            # Clean up
            test_scheduler.register_death()

    @override_settings(
        RQ_QUEUES={
            'async': {
                'DB': REDIS_CONFIG_1.db,
                'HOST': REDIS_CONFIG_1.host,
                'PORT': REDIS_CONFIG_1.port,
                'ASYNC': False,
            }
        }
    )
    def test_get_statistics(self):
        """get_statistics() returns the right number of workers"""
        worker = get_worker('async', name=uuid4().hex)
        worker.register_birth()
        statistics = get_statistics()
        data = statistics['queues'][0]
        self.assertEqual(data['name'], 'async')
        self.assertEqual(data['workers'], 1)
        worker.register_death()

    def test_get_jobs(self):
        """get_jobs() works properly"""
        queue = get_queue('django_rq_test')

        registry = ScheduledJobRegistry(queue.name, queue.connection)
        flush_registry(registry)

        now = datetime.datetime.now()
        job = queue.enqueue_at(now, access_self)
        job2 = queue.enqueue_at(now, access_self)
        self.assertEqual(get_jobs(queue, [job.id, job2.id]), [job, job2])
        self.assertEqual(len(registry), 2)

        # job has been deleted, so the result will be filtered out
        queue.connection.delete(job.key)
        self.assertEqual(get_jobs(queue, [job.id, job2.id]), [job2])
        self.assertEqual(len(registry), 2)

        # If job has been deleted and `registry` is passed,
        # job will also be removed from registry
        queue.connection.delete(job2.key)
        self.assertEqual(get_jobs(queue, [job.id, job2.id], registry), [])
        self.assertEqual(len(registry), 0)

    @override_settings(RQ={'COMMIT_MODE': 'auto'})
    def test_requeue_job(self):
        """requeue_job re-enqueues jobs from any source registry and removes them from it."""
        queue = get_queue('django_rq_test')
        queue.connection.flushdb()

        # FAILED -> requeued
        failed_job = queue.enqueue(failing_job)
        get_worker('django_rq_test').work(burst=True)
        failed_job.refresh()
        self.assertEqual(failed_job.get_status(), JobStatus.FAILED)
        requeue_job(queue, failed_job)
        failed_job.refresh()
        self.assertEqual(failed_job.get_status(), JobStatus.QUEUED)
        self.assertIn(failed_job.id, queue.job_ids)
        self.assertNotIn(failed_job.id, FailedJobRegistry(queue.name, queue.connection).get_job_ids())

        queue.empty()

        # FINISHED -> requeued
        finished_job = queue.enqueue(access_self, result_ttl=500)
        get_worker('django_rq_test').work(burst=True)
        finished_job.refresh()
        self.assertEqual(finished_job.get_status(), JobStatus.FINISHED)
        requeue_job(queue, finished_job)
        finished_job.refresh()
        self.assertEqual(finished_job.get_status(), JobStatus.QUEUED)
        self.assertIn(finished_job.id, queue.job_ids)
        self.assertNotIn(finished_job.id, FinishedJobRegistry(queue.name, queue.connection).get_job_ids())

        queue.empty()

        # SCHEDULED -> requeued
        scheduled_job = queue.enqueue_in(datetime.timedelta(seconds=60), access_self)
        self.assertEqual(scheduled_job.get_status(), JobStatus.SCHEDULED)
        requeue_job(queue, scheduled_job)
        scheduled_job.refresh()
        self.assertEqual(scheduled_job.get_status(), JobStatus.QUEUED)
        self.assertIn(scheduled_job.id, queue.job_ids)
        self.assertNotIn(scheduled_job.id, ScheduledJobRegistry(queue.name, queue.connection).get_job_ids())

        queue.empty()

        # DEFERRED -> requeued (job depending on an unfinished parent)
        parent = queue.enqueue_in(datetime.timedelta(seconds=60), access_self)
        deferred_job = queue.enqueue(access_self, depends_on=parent)
        self.assertEqual(deferred_job.get_status(), JobStatus.DEFERRED)
        requeue_job(queue, deferred_job)
        deferred_job.refresh()
        self.assertEqual(deferred_job.get_status(), JobStatus.QUEUED)
        self.assertIn(deferred_job.id, queue.job_ids)
        self.assertNotIn(deferred_job.id, DeferredJobRegistry(queue.name, queue.connection).get_job_ids())
