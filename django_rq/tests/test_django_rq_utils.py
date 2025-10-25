import datetime
from unittest import TestCase
from unittest.mock import PropertyMock, patch
from uuid import uuid4

from rq.registry import ScheduledJobRegistry

from ..cron import DjangoCronScheduler
from ..queues import get_queue
from ..utils import get_cron_schedulers, get_jobs, get_statistics
from ..workers import get_worker
from .fixtures import access_self
from .utils import flush_registry


class UtilsTest(TestCase):
    def test_get_cron_schedulers(self):
        """Test get_cron_schedulers returns running DjangoCronScheduler instances."""
        from ..queues import get_connection

        # Initially, no schedulers should be running
        schedulers = get_cron_schedulers()
        self.assertIsInstance(schedulers, list)
        initial_count = len(schedulers)

        # Start a test scheduler
        connection = get_connection('default')
        test_scheduler = DjangoCronScheduler(connection=connection, name='test-scheduler')
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
                if scheduler.name == 'test-scheduler':
                    found_scheduler = scheduler

            # Verify our test scheduler was found and has proper data
            self.assertIsNotNone(found_scheduler)
            self.assertIsNotNone(found_scheduler.last_heartbeat)

        finally:
            # Clean up
            test_scheduler.register_death()

    def test_get_statistics(self):
        """get_statistics() returns the right number of workers"""
        queues = [
            {
                'connection_config': {
                    'DB': 0,
                    'HOST': 'localhost',
                    'PORT': 6379,
                },
                'name': 'async',
            }
        ]

        with patch('django_rq.utils.QUEUES_LIST', new_callable=PropertyMock(return_value=queues)):
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
