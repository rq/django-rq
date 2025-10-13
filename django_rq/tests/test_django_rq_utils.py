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
        """Test get_cron_schedulers returns DjangoCronScheduler instances for unique connections."""
        schedulers = get_cron_schedulers()

        self.assertIsInstance(schedulers, list)
        # Base queues yield seven schedulers; installing django-redis adds one more.
        # unittest has assertGreater/assertLess (no assertGreaterThan), so compare against bounds.
        self.assertGreater(len(schedulers), 6)  # equivalent to >= 7
        self.assertLess(len(schedulers), 9)     # equivalent to <= 8

        for scheduler in schedulers:
            self.assertIsInstance(scheduler, DjangoCronScheduler)
            self.assertIsNotNone(scheduler.connection)
            self.assertTrue(hasattr(scheduler.connection, "ping"))

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
