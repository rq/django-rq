import datetime
import sys
import time
from typing import Any, cast
from unittest import mock, skipIf
from unittest.mock import PropertyMock, patch
from uuid import uuid4

import rq
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.safestring import SafeString
from rq import Queue
from rq.job import Job
from rq.registry import FinishedJobRegistry
from rq.serializers import DefaultSerializer, JSONSerializer
from rq.suspension import is_suspended
from rq.worker import Worker

from django_rq import thread_queue
from django_rq.connection_utils import get_connection
from django_rq.decorators import job
from django_rq.jobs import get_job_class
from django_rq.management.commands import rqworker
from django_rq.queues import DjangoRQ, get_queue, get_queues
from django_rq.templatetags.django_rq import force_escape, to_localtime
from django_rq.utils import get_scheduler_pid
from django_rq.workers import get_worker, get_worker_class
from tests.fixtures import DummyJob, DummyQueue, DummyWorker, access_self

try:
    from rq_scheduler import Scheduler

    from django_rq.queues import get_scheduler
    from tests.fixtures import DummyScheduler

    RQ_SCHEDULER_INSTALLED = True
except ImportError:
    RQ_SCHEDULER_INSTALLED = False

QUEUES = settings.RQ_QUEUES


def divide(a, b):
    return a / b


def long_running_job(timeout=10):
    time.sleep(timeout)
    return 'Done sleeping...'


class RqStatsTest(TestCase):
    def test_get_connection_default(self):
        """
        Test that rqstats returns the right statistics
        """
        # Override testing RQ_QUEUES
        queues = [
            {
                'connection_config': {
                    'DB': 0,
                    'HOST': 'localhost',
                    'PORT': 6379,
                },
                'name': 'default',
            }
        ]
        with patch('django_rq.utils.QUEUES_LIST', new_callable=PropertyMock(return_value=queues)):
            # Only to make sure it doesn't crash
            call_command('rqstats')
            call_command('rqstats', '-j')
            call_command('rqstats', '-y')


@override_settings(RQ={'AUTOCOMMIT': True})
class QueuesTest(TestCase):
    def setUp(self):
        """Used to test with / without sentry_sdk available."""
        self.mock_sdk = mock.MagicMock()
        self.mock_sdk.Hub.current.client.options = {}
        sys.modules["sentry_sdk"] = self.mock_sdk

    def tearDown(self):
        del sys.modules["sentry_sdk"]

    def test_get_queue_default(self):
        """
        Test that get_queue use the right parameters for `default`
        connection.
        """
        config = QUEUES['default']
        queue = get_queue('default')
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, 'default')
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    def test_get_queue_url(self):
        """
        Test that get_queue use the right parameters for queues using URL for
        connection.
        """
        queue = get_queue('url')
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, 'url')
        self.assertEqual(connection_kwargs['host'], 'host')
        self.assertEqual(connection_kwargs['port'], 1234)
        self.assertEqual(connection_kwargs['db'], 4)
        self.assertEqual(connection_kwargs['password'], 'password')

    def test_get_queue_url_with_db(self):
        """
        Test that get_queue use the right parameters for queues using URL for
        connection, where URL contains the db number (either as querystring
        or path segment).
        """
        queue = get_queue('url_with_db')
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, 'url_with_db')
        self.assertEqual(connection_kwargs['host'], 'host')
        self.assertEqual(connection_kwargs['port'], 1234)
        self.assertEqual(connection_kwargs['db'], 5)
        self.assertEqual(connection_kwargs['password'], 'password')

    def test_get_queue_url_with_db_default(self):
        """
        Test that get_queue use the right parameters for queues using URL for
        connection, where no DB given and URL does not contain the db number
        (redis-py defaults to 0, should not break).
        """
        queue = get_queue('url_default_db')
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, 'url_default_db')
        self.assertEqual(connection_kwargs['host'], 'host')
        self.assertEqual(connection_kwargs['port'], 1234)
        self.assertEqual(connection_kwargs['db'], None)
        self.assertEqual(connection_kwargs['password'], 'password')

    def test_get_queue_test(self):
        """
        Test that get_queue use the right parameters for `test`
        connection.
        """
        config = QUEUES['test']
        queue = get_queue('test')
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, 'test')
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    def test_get_queues_same_connection(self):
        """
        Checks that getting queues with the same redis connection is ok.
        """
        self.assertEqual(get_queues('test', 'test2'), [get_queue('test'), get_queue('test2')])

    def test_get_queues_different_connections(self):
        """
        Checks that getting queues with different redis connections raise
        an exception.
        """
        self.assertRaises(ValueError, get_queues, 'default', 'test')

    def test_get_queues_different_classes(self):
        """
        Checks that getting queues with different classes (defined in configuration)
        raises an exception.
        """
        self.assertRaises(ValueError, get_queues, 'test', 'test1')

    def test_pass_queue_via_commandline_args(self):
        """
        Checks that passing queues via commandline arguments works
        """
        queue_names = ['django_rq_test', 'django_rq_test2']
        jobs: list[Any] = []
        for queue_name in queue_names:
            queue = get_queue(queue_name)
            jobs.append(
                {
                    'job': queue.enqueue(divide, 42, 1),
                    'finished_job_registry': FinishedJobRegistry(queue.name, queue.connection),
                }
            )

        call_command('rqworker', *queue_names, burst=True)

        for job in jobs:
            self.assertTrue(job['job'].is_finished)
            self.assertIn(job['job'].id, job['finished_job_registry'].get_job_ids())

        # Test with rqworker-pool command
        jobs: list[Any] = []
        for queue_name in queue_names:
            queue = get_queue(queue_name)
            jobs.append(
                {
                    'job': queue.enqueue(divide, 42, 1),
                    'finished_job_registry': FinishedJobRegistry(queue.name, queue.connection),
                }
            )

        call_command('rqworker-pool', *queue_names, burst=True)

        for job in jobs:
            self.assertTrue(job['job'].is_finished)
            self.assertIn(job['job'].id, job['finished_job_registry'].get_job_ids())

    def test_configure_sentry(self):
        rqworker.configure_sentry('https://1@sentry.io/1')
        self.mock_sdk.init.assert_called_once_with(
            'https://1@sentry.io/1',
            ca_certs=None,
            debug=False,
            integrations=[
                self.mock_sdk.integrations.redis.RedisIntegration(),
                self.mock_sdk.integrations.rq.RqIntegration(),
                self.mock_sdk.integrations.django.DjangoIntegration(),
            ],
        )

    def test_configure_sentry__options(self):
        """Check that debug and ca_certs can be passed through to Sentry."""
        rqworker.configure_sentry('https://1@sentry.io/1', sentry_debug=True, sentry_ca_certs='/certs')
        self.mock_sdk.init.assert_called_once_with(
            'https://1@sentry.io/1',
            ca_certs='/certs',
            debug=True,
            integrations=[
                self.mock_sdk.integrations.redis.RedisIntegration(),
                self.mock_sdk.integrations.rq.RqIntegration(),
                self.mock_sdk.integrations.django.DjangoIntegration(),
            ],
        )

    def test_sentry_dsn(self):
        """Check that options are passed to configure_sentry as expected."""
        queue_names = ['django_rq_test']
        call_command(
            'rqworker',
            *queue_names,
            burst=True,
            sentry_dsn='https://1@sentry.io/1',
            sentry_debug=True,
            sentry_ca_certs='/certs',
        )

        self.mock_sdk.init.assert_called_once_with(
            'https://1@sentry.io/1',
            ca_certs='/certs',
            debug=True,
            integrations=[
                self.mock_sdk.integrations.redis.RedisIntegration(),
                self.mock_sdk.integrations.rq.RqIntegration(),
                self.mock_sdk.integrations.django.DjangoIntegration(),
            ],
        )

    @mock.patch('django_rq.management.commands.rqworker.configure_sentry')
    def test_sentry_dsn__noop(self, mocked):
        """Check that sentry is ignored if sentry_dsn is not passed in."""
        queue_names = ['django_rq_test']
        call_command('rqworker', *queue_names, burst=True, sentry_debug=True, sentry_ca_certs='/certs')

        self.assertEqual(mocked.call_count, 0)

    @mock.patch('django_rq.management.commands.rqworker.configure_sentry')
    def test_sentry_sdk_import_error(self, mocked):
        """Check the command handles import errors as expected."""
        mocked.side_effect = ImportError
        queue_names = ['django_rq_test']
        with self.assertRaises(SystemExit):
            call_command('rqworker', *queue_names, burst=True, sentry_dsn='https://1@sentry.io/1')

    # @mock.patch('django_rq.management.commands.rqworker.Connection')
    # def test_connection_error(self, mocked):
    #     """Check that redis ConnectionErrors are handled correctly."""
    #     mocked.side_effect = ConnectionError("Unable to connect")
    #     queue_names = ['django_rq_test']
    #     with self.assertRaises(SystemExit):
    #         call_command('rqworker', *queue_names)

    def test_async(self):
        """
        Checks whether asynchronous settings work
        """
        # Make sure is_async is not set by default
        default_queue = get_queue('default')
        self.assertTrue(default_queue._is_async)

        # Make sure is_async override works
        default_queue_is_async = get_queue('default', is_async=False)
        self.assertFalse(default_queue_is_async._is_async)

        # Make sure old keyword argument 'async' works for backwards
        # compatibility with code expecting older versions of rq or django-rq.
        # Note 'async' is a reserved keyword in Python >= 3.7.
        default_queue_async = get_queue('default', **cast(dict[str, Any], {'async': False}))
        self.assertFalse(default_queue_async._is_async)

        # Make sure is_async setting works
        async_queue = get_queue('async')
        self.assertFalse(async_queue._is_async)

    @override_settings(RQ={'AUTOCOMMIT': False})
    def test_autocommit(self):
        """
        Checks whether autocommit is set properly.
        """
        with self.assertWarns(DeprecationWarning):
            queue = get_queue(autocommit=True)
        self.assertEqual(queue._commit_mode, 'auto')
        with self.assertWarns(DeprecationWarning):
            queue = get_queue(autocommit=False)
        self.assertEqual(queue._commit_mode, 'request_finished')
        # Falls back to default AUTOCOMMIT mode
        queue = get_queue()
        self.assertEqual(queue._commit_mode, 'request_finished')

        queue = get_queue(commit_mode='auto')
        self.assertEqual(queue._commit_mode, 'auto')
        queue = get_queue(commit_mode='request_finished')
        self.assertEqual(queue._commit_mode, 'request_finished')
        queue = get_queue(commit_mode='on_db_commit')
        self.assertEqual(queue._commit_mode, 'on_db_commit')
        with self.assertRaises(ImproperlyConfigured):
            get_queue(commit_mode='later')

        with self.assertWarns(DeprecationWarning):
            queues = get_queues(autocommit=True)
        self.assertEqual(queues[0]._commit_mode, 'auto')
        with self.assertWarns(DeprecationWarning):
            queues = get_queues(autocommit=False)
        self.assertEqual(queues[0]._commit_mode, 'request_finished')
        queues = get_queues()
        self.assertEqual(queues[0]._commit_mode, 'request_finished')

    def test_default_timeout(self):
        """Ensure DEFAULT_TIMEOUT are properly parsed."""
        queue = get_queue()
        self.assertEqual(queue._default_timeout, 500)
        queue = get_queue('test1')
        self.assertEqual(queue._default_timeout, 400)

    def test_get_queue_serializer(self):
        """
        Test that the correct serializer is set on the queue.
        """
        queue = get_queue('test_serializer')
        self.assertEqual(queue.name, 'test_serializer')
        self.assertEqual(queue.serializer, rq.serializers.JSONSerializer)


@override_settings(RQ={'AUTOCOMMIT': True})
class DecoratorTest(TestCase):
    def test_job_decorator(self):
        # Ensure that decorator passes in the right queue from settings.py
        queue_name = 'test3'

        @job(queue_name)
        def test():
            pass

        result = test.delay()
        self.assertEqual(result.origin, queue_name)
        result.delete()

    def test_job_decorator_default(self):
        # Ensure that decorator passes in the right queue from settings.py
        @job
        def test():
            pass

        result = test.delay()
        self.assertEqual(result.origin, 'default')
        result.delete()

    @override_settings(RQ={'AUTOCOMMIT': True, 'DEFAULT_RESULT_TTL': 60})
    def test_job_decorator_with_result_ttl(self):
        # Ensure that decorator result_ttl override the queue DEFAULT_RESULT_TTL and
        # RQ DEFAULT_RESULT_TTL when available
        queue_name = 'test3'
        config = QUEUES[queue_name]

        @job(queue_name, result_ttl=674)
        def test():
            pass

        result = test.delay()
        self.assertEqual(result.result_ttl, 674)
        self.assertNotEqual(config['DEFAULT_RESULT_TTL'], 674)
        result.delete()

    @override_settings(RQ={'AUTOCOMMIT': True, 'DEFAULT_RESULT_TTL': 60})
    def test_job_decorator_queue_result_ttl(self):
        # Ensure the queue DEFAULT_RESULT_TTL is used when the result_ttl is not passed
        queue_name = 'test3'
        config = QUEUES[queue_name]

        @job(queue_name)
        def test():
            pass

        result = test.delay()
        self.assertEqual(result.result_ttl, config['DEFAULT_RESULT_TTL'])
        self.assertNotEqual(config['DEFAULT_RESULT_TTL'], 60)
        result.delete()

    @override_settings(RQ={'AUTOCOMMIT': True, 'DEFAULT_RESULT_TTL': 60})
    def test_job_decorator_queue_without_result_ttl(self):
        # Ensure the RQ DEFAULT_RESULT_TTL is used when the result_ttl is not passed and
        # the queue does not have it either
        queue_name = 'django_rq_test'
        config = QUEUES[queue_name]

        @job(queue_name)
        def test():
            pass

        result = test.delay()
        self.assertIsNone(config.get('DEFAULT_RESULT_TTL'))
        self.assertEqual(result.result_ttl, 60)
        result.delete()

    def test_job_decorator_default_queue_result_ttl(self):
        # Ensure the default queue DEFAULT_RESULT_TTL is used when queue name is not passed

        @job
        def test():
            pass

        result = test.delay()
        self.assertEqual(result.result_ttl, QUEUES['default']['DEFAULT_RESULT_TTL'])
        result.delete()


@override_settings(RQ={'AUTOCOMMIT': True})
class WorkersTest(TestCase):
    def test_get_worker_default(self):
        """
        By default, ``get_worker`` should return worker for ``default`` queue.
        """
        worker = get_worker()
        queue = worker.queues[0]
        self.assertEqual(queue.name, 'default')

    def test_get_worker_specified(self):
        """
        Checks if a worker with specified queues is created when queue
        names are given.
        """
        w = get_worker('test3')
        self.assertEqual(len(w.queues), 1)
        queue = w.queues[0]
        self.assertEqual(queue.name, 'test3')

    def test_get_worker_custom_classes(self):
        w = get_worker(
            job_class='tests.fixtures.DummyJob',
            queue_class='tests.fixtures.DummyQueue',
            worker_class='tests.fixtures.DummyWorker',
        )
        self.assertIs(w.job_class, DummyJob)
        self.assertIsInstance(w.queues[0], DummyQueue)
        self.assertIsInstance(w, DummyWorker)

    def test_get_worker_custom_serializer(self):
        w = get_worker(
            serializer='rq.serializers.JSONSerializer',
        )
        self.assertEqual(w.serializer, JSONSerializer)

    def test_get_worker_default_serializer(self):
        w = get_worker()
        self.assertEqual(w.serializer, DefaultSerializer)

    def test_get_current_job(self):
        """
        Ensure that functions using RQ's ``get_current_job`` doesn't fail
        when run from rqworker (the job id is not in the failed queue).
        """
        queue = get_queue()
        job = queue.enqueue(access_self)
        call_command('rqworker', '--burst')
        failed_queue = Queue(name='failed', connection=queue.connection)
        self.assertFalse(job.id in failed_queue.job_ids)
        job.delete()

    @patch('django_rq.management.commands.rqworker.setup_loghandlers')
    def test_commandline_verbosity_affects_logging_level(self, setup_loghandlers_mock):
        expected_level = {
            0: 'WARNING',
            1: 'INFO',
            2: 'DEBUG',
            3: 'DEBUG',
        }
        for verbosity in [0, 1, 2, 3]:
            setup_loghandlers_mock.reset_mock()
            call_command('rqworker', verbosity=verbosity, burst=True)
            setup_loghandlers_mock.assert_called_once_with(expected_level[verbosity])


@skipIf(RQ_SCHEDULER_INSTALLED is False, 'RQ Scheduler not installed')
class SchedulerTest(TestCase):
    def test_get_scheduler(self):
        """
        Ensure get_scheduler creates a scheduler instance with the right
        connection params for `test` queue.
        """
        config = QUEUES['test']
        scheduler = get_scheduler('test')
        connection_kwargs = scheduler.connection.connection_pool.connection_kwargs
        self.assertEqual(scheduler.queue_name, 'test')
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    def test_get_scheduler_custom_connection(self):
        """
        Ensure get_scheduler respects the `connection` argument.
        """

        with get_connection('test') as connection:
            scheduler = get_scheduler('test', connection=connection)

            self.assertIs(scheduler.connection, connection)

    @patch('django_rq.management.commands.rqscheduler.get_scheduler')
    @patch('django_rq.management.commands.rqscheduler.setup_loghandlers')
    def test_commandline_verbosity_affects_logging_level(self, setup_loghandlers_mock, get_scheduler_mock):
        get_scheduler_mock.run.return_value = None
        expected_level = {
            0: 'WARNING',
            1: 'INFO',
            2: 'DEBUG',
            3: 'DEBUG',
        }
        for verbosity in [0, 1, 2, 3]:
            setup_loghandlers_mock.reset_mock()
            call_command('rqscheduler', verbosity=verbosity)
            setup_loghandlers_mock.assert_called_once_with(expected_level[verbosity])

    @override_settings(RQ={'SCHEDULER_CLASS': 'tests.fixtures.DummyScheduler'})
    def test_scheduler_default(self):
        """
        Scheduler class customization.
        """
        scheduler = get_scheduler('default')
        self.assertIsInstance(scheduler, DummyScheduler)

    @override_settings(RQ={'AUTOCOMMIT': True})
    def test_scheduler_default_timeout(self):
        """
        Ensure scheduler respects DEFAULT_RESULT_TTL value for `result_ttl` param.
        """
        scheduler = get_scheduler('test_scheduler')
        job = scheduler.enqueue_at(datetime.datetime.now() + datetime.timedelta(days=1), divide, 1, 1)
        self.assertTrue(job in scheduler.get_jobs())
        self.assertEqual(job.timeout, 400)
        job.delete()

    @override_settings(RQ={'AUTOCOMMIT': True, 'DEFAULT_RESULT_TTL': 5432})
    def test_scheduler_default_result_ttl(self):
        """
        Ensure scheduler respects DEFAULT_RESULT_TTL value for `result_ttl` param.
        """
        scheduler = get_scheduler('test_scheduler')
        job = scheduler.enqueue_at(datetime.datetime.now() + datetime.timedelta(days=1), divide, 1, 1)
        self.assertTrue(job in scheduler.get_jobs())
        self.assertEqual(job.result_ttl, 5432)
        job.delete()


class JobClassTest(TestCase):
    def test_default_job_class(self):
        job_class = get_job_class()
        self.assertIs(job_class, Job)

    @override_settings(RQ={'JOB_CLASS': 'tests.fixtures.DummyJob'})
    def test_custom_class(self):
        job_class = get_job_class()
        self.assertIs(job_class, DummyJob)

    def test_local_override(self):
        self.assertIs(get_job_class('tests.fixtures.DummyJob'), DummyJob)


class SuspendResumeTest(TestCase):
    def test_suspend_and_resume_commands(self):
        connection = get_connection()
        self.assertEqual(is_suspended(connection), 0)
        call_command('rqsuspend')
        self.assertEqual(is_suspended(connection), 1)
        call_command('rqresume')
        self.assertEqual(is_suspended(connection), 0)


class QueueClassTest(TestCase):
    def test_default_queue_class(self):
        queue = get_queue('test')
        self.assertIsInstance(queue, DjangoRQ)

    def test_for_queue(self):
        queue = get_queue('test1')
        self.assertIsInstance(queue, DummyQueue)

    def test_in_kwargs(self):
        queue = get_queue('test', queue_class=DummyQueue)
        self.assertIsInstance(queue, DummyQueue)


class WorkerClassTest(TestCase):
    def test_default_worker_class(self):
        worker = get_worker()
        self.assertIsInstance(worker, Worker)

    @override_settings(RQ={'WORKER_CLASS': 'tests.fixtures.DummyWorker'})
    def test_custom_class(self):
        worker = get_worker()
        self.assertIsInstance(worker, DummyWorker)

    def test_local_override(self):
        self.assertIs(get_worker_class('tests.fixtures.DummyWorker'), DummyWorker)


@override_settings(RQ={'AUTOCOMMIT': True})
class TemplateTagTest(TestCase):
    def test_to_localtime(self):
        with self.settings(TIME_ZONE='Asia/Jakarta'):
            queue = get_queue()
            job = queue.enqueue(access_self)
            time = to_localtime(job.created_at)

            self.assertIsNotNone(time.tzinfo)
            self.assertEqual(time.strftime("%z"), '+0700')

    def test_force_escape_safe_string(self):
        html = "<h1>hello world</h1>"
        safe_string = SafeString(html)

        escaped_string = force_escape(safe_string)
        expected = "&lt;h1&gt;hello world&lt;/h1&gt;"

        self.assertEqual(escaped_string, expected)

    def test_force_escape_regular_string(self):
        html = "hello world"
        safe_string = SafeString(html)

        escaped_string = force_escape(safe_string)
        expected = "hello world"

        self.assertEqual(escaped_string, expected)


class SchedulerPIDTest(TestCase):
    @skipIf(RQ_SCHEDULER_INSTALLED is False, 'RQ Scheduler not installed')
    def test_scheduler_scheduler_pid_active(self):
        test_queue = 'scheduler_scheduler_active_test'
        queues = [
            {
                'connection_config': {
                    'DB': 0,
                    'HOST': 'localhost',
                    'PORT': 6379,
                },
                'name': test_queue,
            }
        ]
        with patch('django_rq.utils.QUEUES_LIST', new_callable=PropertyMock(return_value=queues)):
            scheduler = get_scheduler(test_queue)
            scheduler.register_birth()
            self.assertIs(get_scheduler_pid(get_queue(scheduler.queue_name)), False)
            scheduler.register_death()

    @skipIf(RQ_SCHEDULER_INSTALLED is False, 'RQ Scheduler not installed')
    def test_scheduler_scheduler_pid_inactive(self):
        test_queue = 'scheduler_scheduler_inactive_test'
        queues = [
            {
                'connection_config': {
                    'DB': 0,
                    'HOST': 'localhost',
                    'PORT': 6379,
                },
                'name': test_queue,
            }
        ]
        with patch('django_rq.utils.QUEUES_LIST', new_callable=PropertyMock(return_value=queues)):
            connection = get_connection(test_queue)
            connection.flushall()  # flush is needed to isolate from other tests
            scheduler = get_scheduler(test_queue)
            scheduler.remove_lock()
            scheduler.register_death()  # will mark the scheduler as death so get_scheduler_pid will return None
            self.assertIs(get_scheduler_pid(get_queue(scheduler.queue_name)), False)

    @skipIf(RQ_SCHEDULER_INSTALLED is True, 'RQ Scheduler installed (no worker--with-scheduler)')
    def test_worker_scheduler_pid_active(self):
        '''The worker works as scheduler too if RQ Scheduler not installed, and the pid scheduler_pid is correct'''
        test_queue = 'worker_scheduler_active_test'
        queues = [
            {
                'connection_config': {
                    'DB': 0,
                    'HOST': 'localhost',
                    'PORT': 6379,
                },
                'name': test_queue,
            }
        ]
        with patch('rq.scheduler.RQScheduler.release_locks'):
            with patch('django_rq.utils.QUEUES_LIST', new_callable=PropertyMock(return_value=queues)):
                queue = get_queue(test_queue)
                worker = get_worker(test_queue, name=uuid4().hex)
                worker.work(with_scheduler=True, burst=True)  # force the worker to acquire a scheduler lock
                pid = get_scheduler_pid(queue)
                self.assertIsNotNone(pid)
                self.assertIsNot(pid, False)
                self.assertIsInstance(pid, int)

    @skipIf(RQ_SCHEDULER_INSTALLED is True, 'RQ Scheduler installed (no worker--with-scheduler)')
    def test_worker_scheduler_pid_inactive(self):
        '''The worker works as scheduler too if RQ Scheduler not installed, and the pid scheduler_pid is correct'''
        test_queue = 'worker_scheduler_inactive_test'
        queues = [
            {
                'connection_config': {
                    'DB': 0,
                    'HOST': 'localhost',
                    'PORT': 6379,
                },
                'name': test_queue,
            }
        ]
        with patch('django_rq.utils.QUEUES_LIST', new_callable=PropertyMock(return_value=queues)):
            worker = get_worker(test_queue, name=uuid4().hex)
            worker.work(
                with_scheduler=False, burst=True
            )  # worker will not acquire lock, scheduler_pid should return None
            self.assertIsNone(get_scheduler_pid(worker.queues[0]))
