import sys
import datetime
import time
from typing import Any, cast, Dict, List
from unittest import skipIf, mock
from unittest.mock import patch, PropertyMock, MagicMock
from uuid import uuid4

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.safestring import SafeString

from redis.exceptions import ConnectionError
from rq import get_current_job, Queue
import rq
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.registry import FinishedJobRegistry, ScheduledJobRegistry
from rq.suspension import is_suspended
from rq.worker import Worker
from rq.serializers import DefaultSerializer, JSONSerializer

from django_rq.decorators import job
from django_rq.jobs import get_job_class
from django_rq.management.commands import rqworker
from django_rq.queues import (
    get_connection,
    get_queue,
    get_queues,
    get_unique_connection_configs,
    DjangoRQ,
    get_redis_connection,
)
from django_rq import thread_queue
from django_rq.templatetags.django_rq import force_escape, to_localtime
from django_rq.tests.fixtures import access_self, DummyJob, DummyQueue, DummyWorker
from django_rq.utils import get_jobs, get_statistics, get_scheduler_pid
from django_rq.workers import get_worker, get_worker_class

try:
    from rq_scheduler import Scheduler
    from ..queues import get_scheduler
    from django_rq.tests.fixtures import DummyScheduler

    RQ_SCHEDULER_INSTALLED = True
except ImportError:
    RQ_SCHEDULER_INSTALLED = False

QUEUES = settings.RQ_QUEUES


def divide(a, b):
    return a / b


def long_running_job(timeout=10):
    time.sleep(timeout)
    return 'Done sleeping...'


def flush_registry(registry):
    connection = registry.connection
    for job_id in registry.get_job_ids():
        connection.zrem(registry.key, job_id)
        try:
            job = Job.fetch(job_id, connection=connection)
            job.delete()
        except NoSuchJobError:
            pass


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

    def test_get_connection_default(self):
        """
        Test that get_connection returns the right connection based for
        `default` queue.
        """
        config = QUEUES['default']
        connection = get_connection()
        connection_kwargs = connection.connection_pool.connection_kwargs
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    def test_get_connection_test(self):
        """
        Test that get_connection returns the right connection based for
        `test` queue.
        """
        config = QUEUES['test']
        connection = get_connection('test')
        connection_kwargs = connection.connection_pool.connection_kwargs
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    @patch('django_rq.queues.Sentinel')
    def test_get_connection_sentinel(self, sentinel_class_mock):
        """
        Test that get_connection returns the right connection based for
        `sentinel` queue.
        """
        sentinel_mock = MagicMock()
        sentinel_mock.master_for.return_value = sentinel_mock
        sentinel_class_mock.side_effect = [sentinel_mock]

        config = QUEUES['sentinel']
        connection = get_connection('sentinel')

        self.assertEqual(connection, sentinel_mock)
        self.assertEqual(sentinel_mock.master_for.call_count, 1)
        self.assertEqual(sentinel_class_mock.call_count, 1)

        sentinel_instances = sentinel_class_mock.call_args[0][0]
        self.assertListEqual(config['SENTINELS'], sentinel_instances)

        connection_kwargs = sentinel_mock.master_for.call_args[1]
        self.assertEqual(connection_kwargs['service_name'], config['MASTER_NAME'])

    @patch('django_rq.queues.Sentinel')
    def test_sentinel_class_initialized_with_kw_args(self, sentinel_class_mock):
        """
        Test that Sentinel object is initialized with proper connection kwargs.
        """
        config = {
            'SENTINELS': [],
            'MASTER_NAME': 'test_master',
            'SOCKET_TIMEOUT': 0.2,
            'DB': 0,
            'USERNAME': 'redis-user',
            'PASSWORD': 'redis-pass',
            'CONNECTION_KWARGS': {'ssl': False},
            'SENTINEL_KWARGS': {'username': 'sentinel-user', 'password': 'sentinel-pass', 'socket_timeout': 0.3},
        }
        get_redis_connection(config)
        sentinel_init_sentinel_kwargs = sentinel_class_mock.call_args[1]
        self.assertDictEqual(
            sentinel_init_sentinel_kwargs,
            {'db': 0, 'username': 'redis-user', 'password': 'redis-pass', 'socket_timeout': 0.2, 'ssl': False, 'sentinel_kwargs': {'username': 'sentinel-user', 'password': 'sentinel-pass', 'socket_timeout': 0.3}}
        )

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
        config = QUEUES['url']
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
        config = QUEUES['url_with_db']
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
        jobs: List[Any] = []
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
        jobs: List[Any] = []
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
            sentry_ca_certs='/certs'
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

    def test_get_unique_connection_configs(self):
        connection_params_1 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        }
        connection_params_2 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 1,
        }
        config = {'default': connection_params_1, 'test': connection_params_2}
        unique_configs = get_unique_connection_configs(config)
        self.assertEqual(len(unique_configs), 2)
        self.assertIn(connection_params_1, unique_configs)
        self.assertIn(connection_params_2, unique_configs)

        # self.assertEqual(get_unique_connection_configs(config),
        #                  [connection_params_1, connection_params_2])
        config = {'default': connection_params_1, 'test': connection_params_1}
        # Should return one connection config since it filters out duplicates
        self.assertEqual(get_unique_connection_configs(config), [connection_params_1])

    def test_get_unique_connection_configs_with_different_timeout(self):
        connection_params_1 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        }
        connection_params_2 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 1,
        }
        queue_params_a = dict(connection_params_1)
        queue_params_b = dict(connection_params_2)
        queue_params_c = dict(connection_params_2)
        queue_params_c["DEFAULT_TIMEOUT"] = 1
        config = {
            'default': queue_params_a,
            'test_b': queue_params_b,
            'test_c': queue_params_c,
        }
        unique_configs = get_unique_connection_configs(config)
        self.assertEqual(len(unique_configs), 2)
        self.assertIn(connection_params_1, unique_configs)
        self.assertIn(connection_params_2, unique_configs)

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
        default_queue_async = get_queue('default', **cast(Dict[str, Any], {'async': False}))
        self.assertFalse(default_queue_async._is_async)

        # Make sure is_async setting works
        async_queue = get_queue('async')
        self.assertFalse(async_queue._is_async)

    @override_settings(RQ={'AUTOCOMMIT': False})
    def test_autocommit(self):
        """
        Checks whether autocommit is set properly.
        """
        queue = get_queue(autocommit=True)
        self.assertTrue(queue._autocommit)
        queue = get_queue(autocommit=False)
        self.assertFalse(queue._autocommit)
        # Falls back to default AUTOCOMMIT mode
        queue = get_queue()
        self.assertFalse(queue._autocommit)

        queues = get_queues(autocommit=True)
        self.assertTrue(queues[0]._autocommit)
        queues = get_queues(autocommit=False)
        self.assertFalse(queues[0]._autocommit)
        queues = get_queues()
        self.assertFalse(queues[0]._autocommit)

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
        config = QUEUES[queue_name]

        @job(queue_name)
        def test():
            pass

        result = test.delay()
        queue = get_queue(queue_name)
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
            job_class='django_rq.tests.fixtures.DummyJob',
            queue_class='django_rq.tests.fixtures.DummyQueue',
            worker_class='django_rq.tests.fixtures.DummyWorker',
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

    @override_settings(RQ={'SCHEDULER_CLASS': 'django_rq.tests.fixtures.DummyScheduler'})
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


class RedisCacheTest(TestCase):
    @skipIf(settings.REDIS_CACHE_TYPE != 'django-redis', 'django-redis not installed')
    @patch('django_redis.get_redis_connection')
    def test_get_queue_django_redis(self, mocked):
        """
        Test that the USE_REDIS_CACHE option for configuration works.
        """
        queue = get_queue('django-redis')
        queue.enqueue(access_self)
        self.assertEqual(len(queue), 1)
        self.assertEqual(mocked.call_count, 1)

    @skipIf(settings.REDIS_CACHE_TYPE != 'django-redis-cache', 'django-redis-cache not installed')
    def test_get_queue_django_redis_cache(self):
        """
        Test that the USE_REDIS_CACHE option for configuration works.
        """
        queueName = 'django-redis-cache'
        queue = get_queue(queueName)
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, queueName)

        cacheHost = settings.CACHES[queueName]['LOCATION'].split(':')[0]
        cachePort = settings.CACHES[queueName]['LOCATION'].split(':')[1]
        cacheDBNum = settings.CACHES[queueName]['OPTIONS']['DB']

        self.assertEqual(connection_kwargs['host'], cacheHost)
        self.assertEqual(connection_kwargs['port'], int(cachePort))
        self.assertEqual(connection_kwargs['db'], int(cacheDBNum))
        self.assertEqual(connection_kwargs['password'], None)


class JobClassTest(TestCase):
    def test_default_job_class(self):
        job_class = get_job_class()
        self.assertIs(job_class, Job)

    @override_settings(RQ={'JOB_CLASS': 'django_rq.tests.fixtures.DummyJob'})
    def test_custom_class(self):
        job_class = get_job_class()
        self.assertIs(job_class, DummyJob)

    def test_local_override(self):
        self.assertIs(get_job_class('django_rq.tests.fixtures.DummyJob'), DummyJob)

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

    @override_settings(RQ={'WORKER_CLASS': 'django_rq.tests.fixtures.DummyWorker'})
    def test_custom_class(self):
        worker = get_worker()
        self.assertIsInstance(worker, DummyWorker)

    def test_local_override(self):
        self.assertIs(get_worker_class('django_rq.tests.fixtures.DummyWorker'), DummyWorker)


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
        queues = [{
            'connection_config': {
                'DB': 0,
                'HOST': 'localhost',
                'PORT': 6379,
            },
            'name': test_queue,
        }]
        with patch('django_rq.utils.QUEUES_LIST',
            new_callable=PropertyMock(return_value=queues)):
            scheduler = get_scheduler(test_queue)
            scheduler.register_birth()
            self.assertIs(get_scheduler_pid(get_queue(scheduler.queue_name)), False)
            scheduler.register_death()

    @skipIf(RQ_SCHEDULER_INSTALLED is False, 'RQ Scheduler not installed')
    def test_scheduler_scheduler_pid_inactive(self):
        test_queue = 'scheduler_scheduler_inactive_test'
        queues = [{
            'connection_config': {
                'DB': 0,
                'HOST': 'localhost',
                'PORT': 6379,
            },
            'name': test_queue,
        }]
        with patch('django_rq.utils.QUEUES_LIST',
            new_callable=PropertyMock(return_value=queues)):
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
        queues = [{
            'connection_config': {
                'DB': 0,
                'HOST': 'localhost',
                'PORT': 6379,
            },
            'name': test_queue,
        }]
        with patch('rq.scheduler.RQScheduler.release_locks') as mock_release_locks:
            with patch('django_rq.utils.QUEUES_LIST',
                new_callable=PropertyMock(return_value=queues)):
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
        queues = [{
            'connection_config': {
                'DB': 0,
                'HOST': 'localhost',
                'PORT': 6379,
            },
            'name': test_queue,
        }]
        with patch('django_rq.utils.QUEUES_LIST',
            new_callable=PropertyMock(return_value=queues)):
            worker = get_worker(test_queue, name=uuid4().hex)
            worker.work(with_scheduler=False, burst=True)  # worker will not acquire lock, scheduler_pid should return None
            self.assertIsNone(get_scheduler_pid(worker.queues[0]))

class UtilsTest(TestCase):
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
