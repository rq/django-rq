import datetime
from unittest import TestCase, skip
from unittest.mock import PropertyMock, patch
from uuid import uuid4

from django.test import override_settings
from rq.registry import ScheduledJobRegistry

from django_rq.cron import DjangoCronScheduler
from django_rq.queues import get_queue
from django_rq.utils import get_cron_schedulers, get_jobs, get_statistics
from django_rq.workers import get_worker
from tests.fixtures import access_self
from tests.utils import flush_registry


class UtilsTest(TestCase):
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

    @override_settings(RQ_QUEUES={'async': {'DB': 0, 'HOST': 'localhost', 'PORT': 6379, 'ASYNC': False}})
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
