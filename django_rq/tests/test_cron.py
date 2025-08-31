from unittest import TestCase

from rq.cron import CronJob

from ..cron import DjangoCronScheduler
from .fixtures import say_hello


class CronTest(TestCase):

    def test_django_cron_scheduler_init(self):
        """Test DjangoCronScheduler can be initialized without connection."""
        scheduler = DjangoCronScheduler()

        # Should not have connection until first register() call
        self.assertIsNone(scheduler.connection)
        self.assertIsNone(scheduler._connection_config)
        self.assertEqual(scheduler._cron_jobs, [])

    def test_first_register_initializes_connection(self):
        """Test that first register() call initializes the scheduler with queue's connection."""
        scheduler = DjangoCronScheduler()

        # Register a job with cron expression (run every minute)
        cron_job = scheduler.register(say_hello, 'default', cron='* * * * *')

        # Should now have connection set
        self.assertIsNotNone(scheduler.connection)
        self.assertIsNotNone(scheduler._connection_config)
        self.assertIsInstance(cron_job, CronJob)
        self.assertEqual(len(scheduler.get_jobs()), 1)

        # Verify cron expression is set correctly
        self.assertEqual(cron_job.cron, '* * * * *')
        self.assertIsNone(cron_job.interval)
        self.assertIsNotNone(cron_job.next_run_time)

    def test_connection_validation(self):
        """Test connection validation for same, compatible, and incompatible queues."""
        # Start with test3 queue (localhost:6379, DB=1)
        scheduler = DjangoCronScheduler()

        # Test 1: Same queue multiple times should work
        job1 = scheduler.register(say_hello, 'test3', interval=60)
        job2 = scheduler.register(say_hello, 'test3', interval=120)

        self.assertEqual(len(scheduler.get_jobs()), 2)
        self.assertEqual(job1.queue_name, 'test3')
        self.assertEqual(job2.queue_name, 'test3')

        # Test 2: Compatible queues (same Redis connection) should work
        # Both 'test3' and 'async' use localhost:6379 with DB=1
        job3 = scheduler.register(say_hello, 'async', interval=180)
        self.assertEqual(len(scheduler.get_jobs()), 3)
        self.assertEqual(job3.queue_name, 'async')

        # Test 3: Incompatible queue (different Redis connection) should fail
        # 'default' uses DB=0 while test3/async use DB=1
        with self.assertRaises(ValueError):
            scheduler.register(say_hello, 'default', interval=240)
