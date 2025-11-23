from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from django_rq import thread_queue
from django_rq.queues import get_commit_mode, get_queue
from tests.fixtures import say_hello
from tests.tests import divide


class CommitModeTest(TestCase):
    @override_settings(RQ={})
    def test_default_commit_mode_is_auto(self):
        self.assertEqual(get_commit_mode(), 'auto')

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
        self.assertEqual(get_commit_mode(), 'auto')

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


class ThreadQueueTest(TestCase):
    @override_settings(RQ={'AUTOCOMMIT': True})
    def test_enqueue_autocommit_on(self):
        """
        Running ``enqueue`` when AUTOCOMMIT is on should
        immediately persist job into Redis.
        """
        queue = get_queue()
        job = queue.enqueue(divide, 1, 1)
        self.assertTrue(job.id in queue.job_ids)
        job.delete()

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
        self.assertEqual(delayed_queue[0][0], queue)
        self.assertEqual(delayed_queue[0][1], ())
        kwargs = delayed_queue[0][2]
        self.assertEqual(kwargs['args'], (1,))
        self.assertEqual(kwargs['result_ttl'], None)
        self.assertEqual(kwargs['kwargs'], {'b': 1})
        self.assertEqual(kwargs['func'], divide)
        self.assertEqual(kwargs['timeout'], None)

    def test_commit(self):
        """
        Ensure that commit_delayed_jobs properly enqueue jobs and clears
        delayed_queue.
        """
        queue = get_queue()
        delayed_queue = thread_queue.get_queue()
        queue.empty()
        self.assertEqual(queue.count, 0)
        queue.enqueue_call(divide, args=(1,), kwargs={'b': 1})
        thread_queue.commit()
        self.assertEqual(queue.count, 1)
        self.assertEqual(len(delayed_queue), 0)

    def test_clear(self):
        queue = get_queue()
        delayed_queue = thread_queue.get_queue()
        delayed_queue.append((queue, divide, (1,), {'b': 1}))
        thread_queue.clear()
        delayed_queue = thread_queue.get_queue()
        self.assertEqual(delayed_queue, [])

    @override_settings(RQ={'AUTOCOMMIT': False})
    def test_success(self):
        queue = get_queue()
        queue.empty()
        thread_queue.clear()
        self.assertEqual(queue.count, 0)
        self.client.get(reverse('success'))
        self.assertEqual(queue.count, 1)

    @override_settings(RQ={'AUTOCOMMIT': False})
    def test_error(self):
        queue = get_queue()
        queue.empty()
        self.assertEqual(queue.count, 0)
        url = reverse('error')
        self.assertRaises(ValueError, self.client.get, url)
        self.assertEqual(queue.count, 0)


@override_settings(RQ={'COMMIT_MODE': 'on_db_commit'})
class OnDbCommitTest(TransactionTestCase):
    """Tests for the on_db_commit commit mode.

    Uses TransactionTestCase because Django's TestCase wraps tests in a
    transaction that never commits, which interferes with on_commit() behavior.
    """

    def test_job_enqueued_after_transaction_commits(self):
        """Job should be enqueued only after the transaction commits."""
        queue = get_queue()
        queue.empty()
        self.assertEqual(queue.count, 0)

        with transaction.atomic():
            queue.enqueue(say_hello)
            # Job should not be in queue yet (transaction not committed)
            self.assertEqual(queue.count, 0)

        # After transaction commits, job should be in queue
        self.assertEqual(queue.count, 1)

    def test_job_discarded_on_rollback(self):
        """Job should be discarded if the transaction rolls back."""
        queue = get_queue()
        queue.empty()
        self.assertEqual(queue.count, 0)

        try:
            with transaction.atomic():
                queue.enqueue(say_hello)
                # Job should not be in queue yet
                self.assertEqual(queue.count, 0)
                # Force a rollback
                raise Exception('Forcing rollback')
        except Exception:
            pass

        # After rollback, job should NOT be in queue
        self.assertEqual(queue.count, 0)

    def test_job_enqueued_immediately_without_transaction(self):
        """Job should be enqueued immediately when not in a transaction.

        Django's on_commit() executes immediately when not in a transaction.
        """
        queue = get_queue()
        queue.empty()
        self.assertEqual(queue.count, 0)

        # No transaction context - should enqueue immediately
        queue.enqueue(say_hello)

        # Job should be in queue immediately
        self.assertEqual(queue.count, 1)

    def test_nested_atomic_blocks(self):
        """Jobs should be enqueued after the outermost transaction commits."""
        queue = get_queue()
        queue.empty()
        self.assertEqual(queue.count, 0)

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
