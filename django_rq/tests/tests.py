import time
import uuid
from unittest import skipIf

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

try:
    from django.urls import reverse
except ImportError:
    from django.core.urlresolvers import reverse

from django.test.client import Client

from django.conf import settings

from mock import patch, PropertyMock
from rq import get_current_job, Queue
from rq.job import Job
from rq.registry import (DeferredJobRegistry, FinishedJobRegistry,
                         StartedJobRegistry)
from rq.worker import Worker

from django_rq.decorators import job
from django_rq.jobs import get_job_class
from django_rq.queues import (
    get_connection, get_queue, get_queue_by_index, get_queues,
    get_unique_connection_configs, DjangoRQ
)
from django_rq import thread_queue
from django_rq.templatetags.django_rq import to_localtime
from django_rq.workers import (get_worker, get_worker_class,
                               collect_workers_by_connection,
                               get_all_workers_by_configuration)


try:
    from rq_scheduler import Scheduler
    from ..queues import get_scheduler
    RQ_SCHEDULER_INSTALLED = True
except ImportError:
    RQ_SCHEDULER_INSTALLED = False

QUEUES = settings.RQ_QUEUES


def access_self():
    return get_current_job().id


def divide(a, b):
    return a / b


def long_running_job(timeout=10):
    time.sleep(timeout)
    return 'Done sleeping...'


def get_failed_queue_index(name='default'):
    """
    Returns the position of FailedQueue for the named queue in QUEUES_LIST
    """
    # Get the index of FailedQueue for 'default' Queue in QUEUES_LIST
    queue_index = None
    connection = get_connection(name)
    connection_kwargs = connection.connection_pool.connection_kwargs
    for i in range(0, 100):
        q = get_queue_by_index(i)
        if q.name == 'failed' and q.connection.connection_pool.connection_kwargs == connection_kwargs:
            queue_index = i
            break

    return queue_index


def get_queue_index(name='default'):
    """
    Returns the position of Queue for the named queue in QUEUES_LIST
    """
    queue_index = None
    connection = get_connection(name)
    connection_kwargs = connection.connection_pool.connection_kwargs
    for i in range(0, 100):
        q = get_queue_by_index(i)
        if q.name == name and q.connection.connection_pool.connection_kwargs == connection_kwargs:
            queue_index = i
            break
    return queue_index


class RqstatsTest(TestCase):

    def test_get_connection_default(self):
        """
        Test that rqstats returns the right statistics
        """
        # Override testing RQ_QUEUES
        queues = [{
            'connection_config': {
                'DB': 0,
                'HOST': 'localhost',
                'PORT': 6379,
            },
            'name': 'default'
        }]
        with patch('django_rq.utils.QUEUES_LIST', new_callable=PropertyMock(return_value=queues)):
            # Only to make sure it doesn't crash
            call_command('rqstats')
            call_command('rqstats', '-j')
            call_command('rqstats', '-y')


@override_settings(RQ={'AUTOCOMMIT': True})
class QueuesTest(TestCase):

    def test_get_connection_default(self):
        """
        Test that get_connection returns the right connection based for
        `defaut` queue.
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
        config = QUEUES['url_default_db']
        queue = get_queue('url_default_db')
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, 'url_default_db')
        self.assertEqual(connection_kwargs['host'], 'host')
        self.assertEqual(connection_kwargs['port'], 1234)
        self.assertEqual(connection_kwargs['db'], 0)
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
        jobs = []
        for queue_name in queue_names:
            queue = get_queue(queue_name)
            jobs.append({
                'job': queue.enqueue(divide, 42, 1),
                'finished_job_registry': FinishedJobRegistry(queue.name, queue.connection),
            })

        call_command('rqworker', *queue_names, burst=True)

        for job in jobs:
            self.assertTrue(job['job'].is_finished)
            self.assertIn(job['job'].id, job['finished_job_registry'].get_job_ids())

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
        config = {
            'default': connection_params_1,
            'test': connection_params_2
        }
        unique_configs = get_unique_connection_configs(config)
        self.assertEqual(len(unique_configs), 2)
        self.assertIn(connection_params_1, unique_configs)
        self.assertIn(connection_params_2, unique_configs)

        # self.assertEqual(get_unique_connection_configs(config),
        #                  [connection_params_1, connection_params_2])
        config = {
            'default': connection_params_1,
            'test': connection_params_1
        }
        # Should return one connection config since it filters out duplicates
        self.assertEqual(get_unique_connection_configs(config),
                         [connection_params_1])

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
        # Make sure async is not set by default
        default_queue = get_queue('default')
        self.assertTrue(default_queue._async)

        # Make sure async override works
        default_queue_async = get_queue('default', async=False)
        self.assertFalse(default_queue_async._async)

        # Make sure async setting works
        async_queue = get_queue('async')
        self.assertFalse(async_queue._async)

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

    def test_job_decorator_result_ttl_default(self):
        from rq.defaults import DEFAULT_RESULT_TTL

        @job
        def test():
            pass
        result = test.delay()
        self.assertEqual(result.result_ttl, DEFAULT_RESULT_TTL)
        result.delete()

    @override_settings(RQ={'AUTOCOMMIT': True, 'DEFAULT_RESULT_TTL': 5432})
    def test_job_decorator_result_ttl(self):
        @job
        def test():
            pass
        result = test.delay()
        self.assertEqual(result.result_ttl, 5432)
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
        w = get_worker('test')
        self.assertEqual(len(w.queues), 1)
        queue = w.queues[0]
        self.assertEqual(queue.name, 'test')

    def test_get_worker_custom_classes(self):
        w = get_worker('test',
                       job_class='django_rq.tests.DummyJob',
                       queue_class='django_rq.tests.DummyQueue',
                       worker_class='django_rq.tests.DummyWorker')
        self.assertIs(w.job_class, DummyJob)
        self.assertIsInstance(w.queues[0], DummyQueue)
        self.assertIsInstance(w, DummyWorker)

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

    def test_collects_worker_various_connections_get_multiple_collection(self):
        queues = [
            {'name': 'default', 'connection_config': settings.RQ_QUEUES['default']},
            {'name': 'django_rq_test', 'connection_config': settings.RQ_QUEUES['django_rq_test']},
            {'name': 'test3', 'connection_config': settings.RQ_QUEUES['test3']},
        ]
        collections = collect_workers_by_connection(queues)
        self.assertEqual(len(collections), 2)


@override_settings(RQ={'AUTOCOMMIT': True})
class ViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('foo', password='pass')
        self.user.is_staff = True
        self.user.is_active = True
        self.user.save()
        self.client = Client()
        self.client.login(username=self.user.username, password='pass')
        get_queue('django_rq_test').connection.flushall()

    def test_requeue_job(self):
        """
        Ensure that a failed job gets requeued when rq_requeue_job is called
        """
        def failing_job():
            raise ValueError

        queue = get_queue('default')
        queue_index = get_failed_queue_index('default')
        job = queue.enqueue(failing_job)
        worker = get_worker('default')
        worker.work(burst=True)
        job.refresh()
        self.assertTrue(job.is_failed)
        self.client.post(reverse('rq_requeue_job', args=[queue_index, job.id]),
                         {'requeue': 'Requeue'})
        self.assertIn(job, queue.jobs)
        job.delete()

    def test_delete_job(self):
        """
        In addition to deleting job from Redis, the job id also needs to be
        deleted from Queue.
        """
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')
        job = queue.enqueue(access_self)
        self.client.post(reverse('rq_delete_job', args=[queue_index, job.id]),
                         {'post': 'yes'})
        self.assertFalse(Job.exists(job.id, connection=queue.connection))
        self.assertNotIn(job.id, queue.job_ids)

    def test_action_delete_jobs(self):
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

        # enqueue some jobs
        job_ids = []
        for _ in range(0, 3):
            job = queue.enqueue(access_self)
            job_ids.append(job.id)

        # remove those jobs using view
        self.client.post(reverse('rq_actions', args=[queue_index]),
                         {'action': 'delete', 'job_ids': job_ids})

        # check if jobs are removed
        for job_id in job_ids:
            self.assertFalse(Job.exists(job_id, connection=queue.connection))
            self.assertNotIn(job_id, queue.job_ids)

    def test_action_requeue_jobs(self):
        def failing_job():
            raise ValueError

        queue = get_queue('django_rq_test')
        failed_queue_index = get_failed_queue_index('django_rq_test')

        # enqueue some jobs that will fail
        jobs = []
        job_ids = []
        for _ in range(0, 3):
            job = queue.enqueue(failing_job)
            jobs.append(job)
            job_ids.append(job.id)

        # do those jobs = fail them
        worker = get_worker('django_rq_test')
        worker.work(burst=True)

        # check if all jobs are really failed
        for job in jobs:
            self.assertTrue(job.is_failed)

        # renqueue failed jobs from failed queue
        self.client.post(reverse('rq_actions', args=[failed_queue_index]),
                         {'action': 'requeue', 'job_ids': job_ids})

        # check if we requeue all failed jobs
        for job in jobs:
            self.assertFalse(job.is_failed)

    def test_clear_queue(self):
        """Test that the queue clear actually clears the queue."""
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')
        job = queue.enqueue(access_self)
        self.client.post(reverse('rq_clear', args=[queue_index]),
                         {'post': 'yes'})
        self.assertFalse(Job.exists(job.id, connection=queue.connection))
        self.assertNotIn(job.id, queue.job_ids)

    def test_finished_jobs(self):
        """Ensure that finished jobs page works properly."""
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

        job = queue.enqueue(access_self)
        registry = FinishedJobRegistry(queue.name, queue.connection)
        registry.add(job, 2)
        response = self.client.get(
            reverse('rq_finished_jobs', args=[queue_index])
        )
        self.assertEqual(response.context['jobs'], [job])

    def test_started_jobs(self):
        """Ensure that active jobs page works properly."""
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

        job = queue.enqueue(access_self)
        registry = StartedJobRegistry(queue.name, queue.connection)
        registry.add(job, 2)
        response = self.client.get(
            reverse('rq_started_jobs', args=[queue_index])
        )
        self.assertEqual(response.context['jobs'], [job])

    def test_deferred_jobs(self):
        """Ensure that active jobs page works properly."""
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

        job = queue.enqueue(access_self)
        registry = DeferredJobRegistry(queue.name, queue.connection)
        registry.add(job, 2)
        response = self.client.get(
            reverse('rq_deferred_jobs', args=[queue_index])
        )
        self.assertEqual(response.context['jobs'], [job])

    def test_get_all_workers(self):
        worker1 = get_worker()
        worker2 = get_worker('test')
        workers_collections = [
            {'config': {'URL': 'redis://'}, 'all_workers': [worker1]},
            {'config': {'URL': 'redis://localhost/1'}, 'all_workers': [worker2]},
        ]
        result = get_all_workers_by_configuration({'URL': 'redis://'}, workers_collections)
        self.assertEqual(result, [worker1])

    def test_workers(self):
        """Worker index page should show workers for a specific queue"""
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

        worker1 = get_worker('django_rq_test', name=uuid.uuid4().hex)
        worker1.register_birth()

        worker2 = get_worker('test3')
        worker2.register_birth()

        response = self.client.get(
            reverse('rq_workers', args=[queue_index])
        )
        self.assertEqual(response.context['workers'], [worker1])

    def test_worker_details(self):
        """Worker index page should show workers for a specific queue"""
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

        worker = get_worker('django_rq_test', name=uuid.uuid4().hex)
        worker.register_birth()

        response = self.client.get(
            reverse('rq_worker_details', args=[queue_index, worker.key])
        )
        self.assertEqual(response.context['worker'], worker)

    def test_statistics_json_view(self):
        """
        Django-RQ's statistic as JSON only viewable by staff or with API_TOKEN
        """

        # Override testing RQ_QUEUES
        queues = [{
            'connection_config': {
                'DB': 0,
                'HOST': 'localhost',
                'PORT': 6379,
            },
            'name': 'default'
        }]
        with patch('django_rq.utils.QUEUES_LIST', new_callable=PropertyMock(return_value=queues)):
            response = self.client.get(reverse('rq_home'))
            self.assertEqual(response.status_code, 200)

            response = self.client.get(reverse('rq_home_json'))
            self.assertEqual(response.status_code, 200)

            # Not staff, only token
            self.user.is_staff = False
            self.user.save()

            response = self.client.get(reverse('rq_home'))
            self.assertEqual(response.status_code, 302)

            # Error, but with 200 code
            response = self.client.get(reverse('rq_home_json'))
            self.assertEqual(response.status_code, 200)
            self.assertIn("error", response.content.decode('utf-8'))

            # With token,
            token = '12345abcde'
            with patch('django_rq.views.API_TOKEN', new_callable=PropertyMock(return_value=token)):
                response = self.client.get(reverse('rq_home_json', args=[token]))
                self.assertEqual(response.status_code, 200)
                self.assertIn("name", response.content.decode('utf-8'))
                self.assertNotIn('"error": true', response.content.decode('utf-8'))

                # Wrong token
                response = self.client.get(reverse('rq_home_json', args=["wrong_token"]))
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("name", response.content.decode('utf-8'))
                self.assertIn('"error": true', response.content.decode('utf-8'))


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


class SchedulerTest(TestCase):

    @skipIf(RQ_SCHEDULER_INSTALLED is False, 'RQ Scheduler not installed')
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


class RedisCacheTest(TestCase):

    @skipIf(settings.REDIS_CACHE_TYPE != 'django-redis',
            'django-redis not installed')
    def test_get_queue_django_redis(self):
        """
        Test that the USE_REDIS_CACHE option for configuration works.
        """
        queueName = 'django-redis'
        queue = get_queue(queueName)
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, queueName)

        cacheHost = settings.CACHES[queueName]['LOCATION'].split(':')[0]
        cachePort = settings.CACHES[queueName]['LOCATION'].split(':')[1]
        cacheDBNum = settings.CACHES[queueName]['LOCATION'].split(':')[2]

        self.assertEqual(connection_kwargs['host'], cacheHost)
        self.assertEqual(connection_kwargs['port'], int(cachePort))
        self.assertEqual(connection_kwargs['db'], int(cacheDBNum))
        self.assertEqual(connection_kwargs['password'], None)

    @skipIf(settings.REDIS_CACHE_TYPE != 'django-redis-cache',
            'django-redis-cache not installed')
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


class DummyJob(Job):
    pass


class JobClassTest(TestCase):

    def test_default_job_class(self):
        job_class = get_job_class()
        self.assertIs(job_class, Job)

    @override_settings(RQ={'JOB_CLASS': 'django_rq.tests.DummyJob'})
    def test_custom_class(self):
        job_class = get_job_class()
        self.assertIs(job_class, DummyJob)

    def test_local_override(self):
        self.assertIs(get_job_class('django_rq.tests.DummyJob'), DummyJob)


class DummyQueue(DjangoRQ):
    """Just Fake class for the following test"""


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


class DummyWorker(Worker):
    pass


class WorkerClassTest(TestCase):

    def test_default_worker_class(self):
        worker = get_worker('test')
        self.assertIsInstance(worker, Worker)

    @override_settings(RQ={'WORKER_CLASS': 'django_rq.tests.DummyWorker'})
    def test_custom_class(self):
        worker = get_worker('test')
        self.assertIsInstance(worker, DummyWorker)

    def test_local_override(self):
        self.assertIs(get_worker_class('django_rq.tests.DummyWorker'), DummyWorker)


@override_settings(RQ={'AUTOCOMMIT': True})
class TemplateTagTest(TestCase):

    def test_to_localtime(self):
        with self.settings(TIME_ZONE='Asia/Jakarta'):
            queue = get_queue()
            job = queue.enqueue(access_self)
            time = to_localtime(job.created_at)

            self.assertIsNotNone(time.tzinfo)
            self.assertEqual(time.strftime("%z"), '+0700')
