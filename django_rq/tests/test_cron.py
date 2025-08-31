import tempfile
import os
from contextlib import suppress
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from rq.cron import CronJob

from ..cron import DjangoCronScheduler
from ..management.commands.rqcron import Command as RqcronCommand
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

        # Same queue multiple times should work
        job1 = scheduler.register(say_hello, 'test3', interval=60)
        job2 = scheduler.register(say_hello, 'test3', interval=120)

        self.assertEqual(len(scheduler.get_jobs()), 2)
        self.assertEqual(job1.queue_name, 'test3')
        self.assertEqual(job2.queue_name, 'test3')

        # Compatible queues (same Redis connection) should work
        # Both 'test3' and 'async' use localhost:6379 with DB=1
        job3 = scheduler.register(say_hello, 'async', interval=180)
        self.assertEqual(len(scheduler.get_jobs()), 3)
        self.assertEqual(job3.queue_name, 'async')

        # Queues having different Redis connections should fail
        # 'default' uses DB=0 while test3/async use DB=1
        with self.assertRaises(ValueError):
            scheduler.register(say_hello, 'default', interval=240)

        # Undefined queue_name should fail
        scheduler = DjangoCronScheduler()
        with self.assertRaises(KeyError):
            scheduler.register(say_hello, 'nonexistent_queue', interval=300)


class CronCommandTest(TestCase):

    def tearDown(self):
        """Clear the global job registry and module cache after each test."""
        import sys

        # Remove test config modules from cache so they can be re-imported
        for module_name in ['django_rq.tests.cron_config1', 'django_rq.tests.cron_config2']:
            if module_name in sys.modules:
                del sys.modules[module_name]

    @patch('django_rq.cron.DjangoCronScheduler.start')
    def test_rqcron_command(self, mock_start):
        """Test rqcron command execution: success, file not found, and import errors."""
        mock_start.return_value = None

        # Test 1: Successful execution
        out = StringIO()
        config_path = 'django_rq.tests.cron_config1'

        call_command('rqcron', config_path, stdout=out)

        output = out.getvalue()
        self.assertIn(f'Loading cron configuration from {config_path}', output)
        self.assertIn('Starting cron scheduler with 2 jobs...', output)
        mock_start.assert_called_once()

        # Test 2: File not found
        err = StringIO()
        with self.assertRaises(SystemExit):
            call_command('rqcron', 'nonexistent_file.py', stderr=err)

        # Verify it's a FileNotFoundError by checking the error message
        self.assertIn("Configuration file not found", err.getvalue())

        # Test 3: Import error
        err = StringIO()
        with self.assertRaises(SystemExit):
            call_command('rqcron', 'nonexistent.module.path', stderr=err)

        # Verify it's an ImportError by checking the error message
        self.assertIn("Failed to import configuration", err.getvalue())

    @patch('django_rq.cron.DjangoCronScheduler.start')
    @patch('django_rq.cron.DjangoCronScheduler.load_config_from_file')
    def test_rqcron_command_exceptions(self, mock_load_config, mock_start):
        """Test rqcron command exception handling."""
        mock_load_config.return_value = None

        # Test KeyboardInterrupt handling
        mock_start.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit):
            call_command('rqcron', 'django_rq.tests.cron_config2')

        # Test general exception handling
        mock_load_config.side_effect = Exception("Test error")
        with self.assertRaises(SystemExit):
            call_command('rqcron', 'django_rq.tests.cron_config2')

    def test_rqcron_command_successful_run(self):
        """Test successful rqcron command execution without mocking."""
        out = StringIO()
        config_path = 'django_rq.tests.cron_config1'

        # Use a very short timeout to test actual execution
        import signal

        def timeout_handler(signum, frame):
            raise KeyboardInterrupt()

        # Set up a timeout to stop the command after a short time
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(1)  # Stop after 1 second

        try:
            # The command will be interrupted and may or may not raise SystemExit depending on Django version
            with suppress(SystemExit):
                call_command('rqcron', config_path, stdout=out)
        finally:
            signal.alarm(0)  # Cancel the alarm
            signal.signal(signal.SIGALRM, old_handler)

        output = out.getvalue()
        self.assertIn(f'Loading cron configuration from {config_path}', output)
        self.assertIn('Starting cron scheduler with 2 jobs...', output)
