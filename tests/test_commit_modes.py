from datetime import datetime, timedelta, timezone
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rq.registry import ScheduledJobRegistry

from django_rq import thread_queue
from django_rq.queues import get_commit_mode, get_queue
from tests.fixtures import say_hello
from tests.tests import divide
from tests.utils import flush_registry


class CommitModeTest(TestCase):
    @override_settings(RQ={})
    def test_default_commit_mode_is_on_db_commit(self):
        self.assertEqual(get_commit_mode(), 'on_db_commit')

    @override_settings(RQ={'COMMIT_MODE': 'auto'})
    def test_commit_mode_auto_explicit(self):
        self.assertEqual(get_commit_mode(), 'auto')

    @override_settings(RQ={'COMMIT_MODE': 'request_finished'})
    def test_commit_mode_request_finished(self):
        self.assertEqual(get_commit_mode(), 'request_finished')

    @override_settings(RQ={'COMMIT_MODE': 'on_db_commit'})
    def test_commit_mode_on_db_commit(self):
        self.assertEqual(get_commit_mode(), 'on_db_commit')

    @override_settings(RQ={'AUTOCOMMIT': False})
    def test_autocommit_fallback_with_warning(self):
        with self.assertWarns(DeprecationWarning):
            mode = get_commit_mode()
        self.assertEqual(mode, 'request_finished')

    @override_settings(RQ={'COMMIT_MODE': ''})
    def test_commit_mode_empty_string_falls_back(self):
        self.assertEqual(get_commit_mode(), 'on_db_commit')

    @override_settings(RQ={'COMMIT_MODE': 123})
    def test_commit_mode_invalid_type(self):
        with self.assertRaises(ImproperlyConfigured):
            get_commit_mode()

    @override_settings(RQ={'COMMIT_MODE': True})
    def test_commit_mode_invalid_bool(self):
        with self.assertRaises(ImproperlyConfigured):
            get_commit_mode()

    @override_settings(RQ={'COMMIT_MODE': 'later'})
    def test_commit_mode_invalid_value(self):
        with self.assertRaises(ImproperlyConfigured):
            get_commit_mode()


def reset_state(queue):
    """Empty the queue, its scheduled registry and the thread-local delayed queue."""
    queue.empty()
    flush_registry(ScheduledJobRegistry(queue=queue))
    thread_queue.clear()


class ThreadQueueTest(TestCase):
    """Tests for the request_finished commit mode (the test settings default via AUTOCOMMIT=False)."""

    def setUp(self):
        queue = get_queue()
        reset_state(queue)
        self.addCleanup(reset_state, queue)

    @override_settings(RQ={'AUTOCOMMIT': True})
    def test_enqueue_autocommit_on(self):
        """
        Running ``enqueue`` when AUTOCOMMIT is on should
        immediately persist job into Redis.
        """
        queue = get_queue()
        registry = ScheduledJobRegistry(queue=queue)
        job = queue.enqueue(divide, 1, 1)
        self.assertTrue(job.id in queue.job_ids)

        # The scheduling APIs also run immediately and return the Job
        scheduled = queue.enqueue_at(datetime(2030, 1, 1, tzinfo=timezone.utc), say_hello)
        self.assertIn(scheduled.id, registry.get_job_ids())
        scheduled = queue.enqueue_in(timedelta(minutes=1), say_hello)
        self.assertIn(scheduled.id, registry.get_job_ids())
        self.assertEqual(thread_queue.get_queue(), [])

    @override_settings(RQ={'AUTOCOMMIT': False})
    def test_enqueue_autocommit_off(self):
        """
        Running ``enqueue`` when AUTOCOMMIT is off should
        put the job in the delayed queue instead of enqueueing it right away.
        """
        queue = get_queue()
        job = queue.enqueue(divide, 1, b=1)
        self.assertTrue(job is None)
        delayed_queue = thread_queue.get_queue()
        deferred_queue, method_name, args, kwargs = delayed_queue[0]
        # The deferred call is RQ's own enqueue_job on this queue
        self.assertIs(deferred_queue, queue)
        self.assertEqual(method_name, 'enqueue_job')
        self.assertEqual(kwargs['pipeline'], None)
        # The Job is created at call time; only the Redis write is deferred
        deferred_job = args[0]
        self.assertEqual(deferred_job.func, divide)
        self.assertEqual(deferred_job.args, (1,))
        self.assertEqual(deferred_job.kwargs, {'b': 1})
        self.assertEqual(deferred_job.result_ttl, None)
        self.assertEqual(deferred_job.timeout, queue._default_timeout)

        # enqueue_at is deferred the same way
        scheduled_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.assertIsNone(queue.enqueue_at(scheduled_at, say_hello))
        deferred_queue, method_name, args, kwargs = delayed_queue[1]
        self.assertIs(deferred_queue, queue)
        self.assertEqual(method_name, 'enqueue_at')
        self.assertEqual(args, (scheduled_at, say_hello))

        # enqueue_in goes through RQ's enqueue_at, so it is recorded as 'enqueue_at'
        # with the target datetime already resolved
        self.assertIsNone(queue.enqueue_in(timedelta(minutes=1), say_hello))
        deferred_queue, method_name, args, kwargs = delayed_queue[2]
        self.assertIs(deferred_queue, queue)
        self.assertEqual(method_name, 'enqueue_at')
        self.assertIsInstance(args[0], datetime)
        self.assertEqual(args[1], say_hello)

        self.assertEqual(queue.count, 0)
        self.assertEqual(len(ScheduledJobRegistry(queue=queue)), 0)

    def test_commit(self):
        """
        Ensure that commit_delayed_jobs properly enqueue jobs and clears
        delayed_queue.
        """
        queue = get_queue()
        registry = ScheduledJobRegistry(queue=queue)
        delayed_queue = thread_queue.get_queue()
        self.assertEqual(queue.count, 0)

        fixed_now = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        delay = timedelta(minutes=5)
        with mock.patch('rq.queue.now', return_value=fixed_now) as mocked_now:
            queue.enqueue_call(divide, args=(1,), kwargs={'b': 1})
            queue.enqueue_in(delay, say_hello)
            # Time passes before the request finishes
            mocked_now.return_value = fixed_now + timedelta(hours=1)
            thread_queue.commit()

        self.assertEqual(queue.count, 1)
        self.assertEqual(len(delayed_queue), 0)
        self.assertEqual(len(registry), 1)
        # enqueue_in resolves its target time when called, not when committed
        scheduled_job_id = registry.get_job_ids()[0]
        self.assertEqual(registry.get_scheduled_time(scheduled_job_id), fixed_now + delay)

    def test_clear(self):
        queue = get_queue()
        delayed_queue = thread_queue.get_queue()
        job = queue.create_job(divide, args=(1,), kwargs={'b': 1})
        delayed_queue.append((queue, 'enqueue_job', (job,), {}))
        thread_queue.clear()
        delayed_queue = thread_queue.get_queue()
        self.assertEqual(delayed_queue, [])

    def test_enqueue_now(self):
        """enqueue_now runs RQ's own method right away, ignoring the commit mode."""
        queue = get_queue()
        registry = ScheduledJobRegistry(queue=queue)
        scheduled = queue.enqueue_now('enqueue_at', datetime(2030, 1, 1, tzinfo=timezone.utc), say_hello)
        self.assertIn(scheduled.id, registry.get_job_ids())
        self.assertEqual(thread_queue.get_queue(), [])

    def test_explicit_pipeline_runs_immediately(self):
        """A caller-supplied pipeline is never deferred."""
        queue = get_queue()
        registry = ScheduledJobRegistry(queue=queue)
        with queue.connection.pipeline() as pipeline:
            job = queue.enqueue(say_hello, pipeline=pipeline)
            scheduled = queue.enqueue_at(datetime(2030, 1, 1, tzinfo=timezone.utc), say_hello, pipeline=pipeline)
            self.assertIsNotNone(job)
            self.assertIsNotNone(scheduled)
            self.assertEqual(thread_queue.get_queue(), [])
            # The jobs only reach the queue once the caller executes the pipeline
            self.assertEqual(queue.count, 0)
            pipeline.execute()

        self.assertIn(job.id, queue.job_ids)
        self.assertIn(scheduled.id, registry.get_job_ids())

    @override_settings(RQ={'AUTOCOMMIT': False})
    def test_success(self):
        queue = get_queue()
        registry = ScheduledJobRegistry(queue=queue)
        self.assertEqual(queue.count, 0)
        self.client.get(reverse('success'))
        self.assertEqual(queue.count, 1)
        self.assertEqual(len(registry), 1)

    @override_settings(RQ={'AUTOCOMMIT': False})
    def test_error(self):
        queue = get_queue()
        registry = ScheduledJobRegistry(queue=queue)
        self.assertEqual(queue.count, 0)
        url = reverse('error')
        self.assertRaises(ValueError, self.client.get, url)
        self.assertEqual(queue.count, 0)
        self.assertEqual(len(registry), 0)


@override_settings(RQ={'COMMIT_MODE': 'on_db_commit'})
class OnDbCommitTest(TransactionTestCase):
    """Tests for the on_db_commit commit mode.

    Uses TransactionTestCase because Django's TestCase wraps tests in a
    transaction that never commits, which interferes with on_commit() behavior.
    """

    def setUp(self):
        self.queue = get_queue()
        self.registry = ScheduledJobRegistry(queue=self.queue)
        reset_state(self.queue)
        self.addCleanup(reset_state, self.queue)

    def enqueue_with_every_api(self):
        """Call enqueue, enqueue_at and enqueue_in once each, using the API name as the job id."""
        queue = self.queue
        job = queue.enqueue(say_hello, job_id='enqueue')
        scheduled = queue.enqueue_at(datetime(2030, 1, 1, tzinfo=timezone.utc), say_hello, job_id='enqueue_at')
        delayed = queue.enqueue_in(timedelta(minutes=1), say_hello, job_id='enqueue_in')
        return job, scheduled, delayed

    def test_job_enqueued_after_transaction_commits(self):
        """Jobs should be enqueued or scheduled only after the transaction commits."""
        with transaction.atomic():
            job, scheduled, delayed = self.enqueue_with_every_api()
            # Inside transaction, every API returns None (deferred via on_commit)
            self.assertIsNone(job)
            self.assertIsNone(scheduled)
            self.assertIsNone(delayed)
            self.assertEqual(self.queue.count, 0)

        # After transaction commits, enqueue is queued, enqueue_at + enqueue_in are scheduled
        self.assertEqual(self.queue.job_ids, ['enqueue'])
        self.assertEqual(sorted(self.registry.get_job_ids()), ['enqueue_at', 'enqueue_in'])

    def test_job_discarded_on_rollback(self):
        """Jobs should be discarded if the transaction rolls back."""
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.enqueue_with_every_api()
                self.assertEqual(self.queue.count, 0)
                raise RuntimeError('Forcing rollback')

        # After rollback, nothing should be in Redis
        self.assertEqual(self.queue.count, 0)

    def test_job_enqueued_immediately_without_transaction(self):
        """Jobs should be enqueued immediately when not in a transaction.

        When not in an atomic block, each API should return the Job object
        and write to Redis immediately (short-circuit optimization).
        """
        job, scheduled, delayed = self.enqueue_with_every_api()
        self.assertIn(job.id, self.queue.job_ids)
        self.assertIn(scheduled.id, self.registry.get_job_ids())
        self.assertIn(delayed.id, self.registry.get_job_ids())

    def test_nested_atomic_blocks(self):
        """Jobs should be enqueued after the outermost transaction commits."""
        queue = self.queue
        with transaction.atomic():
            queue.enqueue(say_hello)
            with transaction.atomic():
                queue.enqueue(say_hello)
                # Neither job should be in queue yet
                self.assertEqual(queue.count, 0)
            # Still not committed - outer transaction not done
            self.assertEqual(queue.count, 0)

        # After outermost transaction commits, both jobs should be in queue
        self.assertEqual(queue.count, 2)
