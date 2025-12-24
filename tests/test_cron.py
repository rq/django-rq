from contextlib import suppress
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.test.client import Client
from django.urls import reverse
from rq.cron import CronJob

from django_rq.cron import DjangoCronScheduler
from tests.fixtures import say_hello


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
        cron_job = scheduler.register(say_hello, "default", cron="* * * * *")

        # Should now have connection set
        self.assertIsNotNone(scheduler.connection)
        self.assertIsNotNone(scheduler._connection_config)
        self.assertIsInstance(cron_job, CronJob)
        self.assertEqual(len(scheduler.get_jobs()), 1)

        # Verify cron expression is set correctly
        self.assertEqual(cron_job.cron, "* * * * *")
        self.assertIsNone(cron_job.interval)
        # self.assertIsNotNone(cron_job.next_run_time)

    def test_connection_validation(self):
        """Test connection validation for same, compatible, and incompatible queues."""
        # Start with test3 queue (secondary Redis DB configured for tests)
        scheduler = DjangoCronScheduler()

        # Same queue multiple times should work
        job1 = scheduler.register(say_hello, "test3", interval=60)
        job2 = scheduler.register(say_hello, "test3", interval=120)

        self.assertEqual(len(scheduler.get_jobs()), 2)
        self.assertEqual(job1.queue_name, "test3")
        self.assertEqual(job2.queue_name, "test3")

        # Compatible queues (same Redis connection) should work
        # Both 'test3' and 'async' share the same Redis connection settings
        job3 = scheduler.register(say_hello, "async", interval=180)
        self.assertEqual(len(scheduler.get_jobs()), 3)
        self.assertEqual(job3.queue_name, "async")

        # Queues having different Redis connections should fail
        with self.assertRaises(ValueError):
            scheduler.register(say_hello, "default", interval=240)

        # Undefined queue_name should fail
        scheduler = DjangoCronScheduler()
        with self.assertRaises(KeyError):
            scheduler.register(say_hello, "nonexistent_queue", interval=300)

    def test_connection_index_property(self):
        """Test connection_index property returns correct index or raises appropriate exceptions."""

        scheduler = DjangoCronScheduler()

        # Before any registration, connection_index should raise ValueError
        with self.assertRaises(ValueError):
            _ = scheduler.connection_index

        # Register a job with 'test3' queue (secondary Redis DB configured for tests)
        scheduler.register(say_hello, "test3", interval=60)

        # Now connection_index should return a valid index
        connection_index = scheduler.connection_index
        self.assertGreaterEqual(connection_index, 0)

        # Test with a queue using a different connection
        scheduler2 = DjangoCronScheduler()
        scheduler2.register(say_hello, "default", interval=60)  # Uses DB=0

        # Should have a different connection_index
        self.assertNotEqual(scheduler2.connection_index, scheduler.connection_index)


class CronCommandTest(TestCase):
    @patch('django_rq.cron.DjangoCronScheduler.start')
    def test_rqcron_command(self, mock_start):
        """Test rqcron command execution: success and import errors from load_config_from_file."""
        mock_start.return_value = None

        # Test 1: Successful execution
        out = StringIO()
        config_path = "tests.cron_config1"

        call_command("rqcron", config_path, stdout=out)

        output = out.getvalue()
        self.assertIn(f"Loading cron configuration from {config_path}", output)
        self.assertIn("Starting cron scheduler with 2 jobs...", output)
        mock_start.assert_called_once()

        # Test 2: File not found - should raise ImportError from RQ
        with self.assertRaises(ImportError) as cm:
            call_command("rqcron", "nonexistent_file.py")

        self.assertIn("No module named 'nonexistent_file'", str(cm.exception))

        # Test 3: Import error
        with self.assertRaises(ImportError) as cm:
            call_command("rqcron", "nonexistent.module.path")

        self.assertIn("No module named 'nonexistent'", str(cm.exception))

    @patch("django_rq.cron.DjangoCronScheduler.start")
    @patch("django_rq.cron.DjangoCronScheduler.load_config_from_file")
    def test_rqcron_command_exceptions(self, mock_load_config, mock_start):
        """Test rqcron command exception handling."""
        mock_load_config.return_value = None

        # Test KeyboardInterrupt handling
        mock_start.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit):
            call_command("rqcron", "tests.cron_config2")

        # Test general exception handling - should bubble up as raw exception
        mock_load_config.side_effect = Exception("Test error")
        with self.assertRaises(Exception) as cm:
            call_command("rqcron", "tests.cron_config2")

        self.assertEqual(str(cm.exception), "Test error")

    def test_rqcron_command_successful_run(self):
        """Test successful rqcron command execution without mocking."""
        out = StringIO()
        config_path = "tests.cron_config1"

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
                call_command("rqcron", config_path, stdout=out)
        finally:
            signal.alarm(0)  # Cancel the alarm
            signal.signal(signal.SIGALRM, old_handler)

        output = out.getvalue()
        self.assertIn(f"Loading cron configuration from {config_path}", output)
        self.assertIn("Starting cron scheduler with 2 jobs...", output)


@override_settings(ROOT_URLCONF='tests.default_with_custom_mount_urls')
class CronViewTest(TestCase):
    def setUp(self):
        """Set up test user and client."""
        self.user = User.objects.create_user('foo', password='pass', is_staff=True, is_active=True)
        self.client = Client()
        self.client.login(username=self.user.username, password='pass')

    def test_cron_scheduler_detail_view(self):
        """Test cron scheduler detail view with various scenarios."""
        # Create a real scheduler and register it
        scheduler = DjangoCronScheduler(name='test-scheduler')
        scheduler.register(say_hello, "default", interval=60)
        scheduler.register_birth()

        for prefix in ('admin:django_rq_', 'django_rq:'):
            # Test 1: Successful view of existing scheduler
            connection_index = scheduler.connection_index
            url = reverse(f'{prefix}cron_scheduler_detail', args=[connection_index, 'test-scheduler'])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['scheduler'].name, 'test-scheduler')
            self.assertContains(response, 'test-scheduler')

            # Test 2: Non-existent scheduler returns 404
            url = reverse(f'{prefix}cron_scheduler_detail', args=[connection_index, 'nonexistent-scheduler'])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404)

            # Test 3: Invalid connection index returns 404
            url = reverse(f'{prefix}cron_scheduler_detail', args=[999, 'test-scheduler'])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404)

        # Clean up
        scheduler.register_death()
