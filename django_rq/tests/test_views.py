import uuid

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.test.client import Client

try:
    from django.urls import reverse
except ImportError:
    from django.core.urlresolvers import reverse

from mock import patch, PropertyMock

from rq.job import Job, JobStatus
from rq.registry import (DeferredJobRegistry, FailedJobRegistry,
                         FinishedJobRegistry, StartedJobRegistry)

from django_rq import get_queue
from django_rq.workers import get_worker
from django_rq.tests.fixtures import access_self
from .utils import get_queue_index


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

    def test_jobs(self):
        """Jobs in queue are displayed properly"""
        queue = get_queue('default')
        job = queue.enqueue(access_self)
        queue_index = get_queue_index('default')
        response = self.client.get(reverse('rq_jobs', args=[queue_index]))
        self.assertEqual(response.context['jobs'], [job])

        # This page shouldn't fail when job.data is corrupt
        queue.connection.hset(job.key, 'data', 'unpickleable data')
        response = self.client.get(reverse('rq_jobs', args=[queue_index]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('UnpicklingError', response.content.decode('utf-8'))

    def test_job_details(self):
        """Job data is displayed properly"""
        queue = get_queue('default')
        job = queue.enqueue(access_self)
        queue_index = get_queue_index('default')

        url = reverse('rq_job_detail', args=[queue_index, job.id])
        response = self.client.get(url)
        self.assertEqual(response.context['job'], job)

        # This page shouldn't fail when job.data is corrupt
        queue.connection.hset(job.key, 'data', 'unpickleable data')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('UnpicklingError', response.content.decode('utf-8'))

    def test_requeue_job(self):
        """
        Ensure that a failed job gets requeued when rq_requeue_job is called
        """
        def failing_job():
            raise ValueError

        queue = get_queue('default')
        queue_index = get_queue_index('default')
        job = queue.enqueue(failing_job)
        worker = get_worker('default')
        worker.work(burst=True)
        job.refresh()
        self.assertTrue(job.is_failed)
        self.client.post(reverse('rq_requeue_job', args=[queue_index, job.id]),
                         {'requeue': 'Requeue'})
        self.assertIn(job, queue.jobs)
        job.delete()
    
    def test_requeue_all(self):
        """
        Ensure that requeueing all failed job work properly
        """
        def failing_job():
            raise ValueError

        queue = get_queue('default')
        queue_index = get_queue_index('default')
        job = queue.enqueue(failing_job)
        queue.enqueue(failing_job)
        worker = get_worker('default')
        worker.work(burst=True)

        response = self.client.get(reverse('rq_requeue_all', args=[queue_index]))
        self.assertEqual(response.context['total_jobs'], 2)
        # After requeue_all is called, jobs are enqueued
        response = self.client.post(reverse('rq_requeue_all', args=[queue_index]))
        self.assertEqual(len(queue), 2)

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

    def test_enqueue_jobs(self):
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

        # enqueue some jobs that depends on other
        previous_job = None
        for _ in range(0, 3):
            job = queue.enqueue(access_self, depends_on=previous_job)
            previous_job = job

        # This job is deffered
        last_job = job
        self.assertEqual(last_job.get_status(), JobStatus.DEFERRED)
        self.assertIsNone(last_job.enqueued_at)

        # We want to force-enqueue this job
        self.client.post(reverse('rq_enqueue_job', args=[queue_index, last_job.id]))

        # Check that job is updated correctly
        last_job = queue.fetch_job(last_job.id)
        self.assertEqual(last_job.get_status(), JobStatus.QUEUED)
        self.assertIsNotNone(last_job.enqueued_at)

    def test_action_requeue_jobs(self):
        def failing_job():
            raise ValueError

        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

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
        self.client.post(reverse('rq_actions', args=[queue_index]),
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

    def test_failed_jobs(self):
        """Ensure that failed jobs page works properly."""
        queue = get_queue('django_rq_test')
        queue_index = get_queue_index('django_rq_test')

        # Test that page doesn't fail when FailedJobRegistry is empty
        response = self.client.get(
            reverse('rq_failed_jobs', args=[queue_index])
        )
        self.assertEqual(response.status_code, 200)

        job = queue.enqueue(access_self)
        registry = FailedJobRegistry(queue.name, queue.connection)
        registry.add(job, 2)
        response = self.client.get(
            reverse('rq_failed_jobs', args=[queue_index])
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

    def test_workers(self):
        """Worker index page should show workers for a specific queue"""
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
        with patch('django_rq.utils.QUEUES_LIST',
                   new_callable=PropertyMock(return_value=queues)):
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
