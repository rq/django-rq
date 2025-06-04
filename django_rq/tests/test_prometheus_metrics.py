import os
from unittest import skipIf
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.test.client import Client
from django.urls import NoReverseMatch, reverse

from django_rq import get_queue
from django_rq.workers import get_worker

from .fixtures import access_self, failing_job

try:
    import prometheus_client
except ImportError:
    prometheus_client = None

RQ_QUEUES = {
    'default': {
        'HOST': os.environ.get('REDIS_HOST', 'localhost'),
        'PORT': 6379,
        'DB': 0,
    },
}


@skipIf(prometheus_client is None, 'prometheus_client is required')
@override_settings(RQ={'AUTOCOMMIT': True})
class PrometheusTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('foo', password='pass')
        self.user.is_staff = True
        self.user.is_active = True
        self.user.save()
        self.client = Client()
        self.client.force_login(self.user)
        get_queue('default').connection.flushall()

    def assertMetricsContain(self, lines):
        response = self.client.get(reverse('rq_metrics'))
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(
            lines, set(response.content.decode('utf-8').splitlines())
        )

    @patch('django_rq.settings.QUEUES', RQ_QUEUES)
    def test_metrics_default(self):
        self.assertMetricsContain(
            {
                '# HELP rq_jobs RQ jobs by status',
                'rq_jobs{queue="default",status="queued"} 0.0',
                'rq_jobs{queue="default",status="started"} 0.0',
                'rq_jobs{queue="default",status="finished"} 0.0',
                'rq_jobs{queue="default",status="failed"} 0.0',
                'rq_jobs{queue="default",status="deferred"} 0.0',
                'rq_jobs{queue="default",status="scheduled"} 0.0',
            }
        )

    @patch('django_rq.settings.QUEUES', RQ_QUEUES)
    def test_metrics_with_jobs(self):
        queue = get_queue('default')
        queue.enqueue(failing_job)

        for _ in range(10):
            queue.enqueue(access_self)

        worker = get_worker('default', name='test_worker')
        worker.register_birth()

        # override worker registration to effectively simulate non burst mode
        register_death = worker.register_death
        worker.register_birth = worker.register_death = lambda: None  # type: ignore[method-assign]

        try:
            self.assertMetricsContain(
                {
                    # job information
                    '# HELP rq_jobs RQ jobs by status',
                    'rq_jobs{queue="default",status="queued"} 11.0',
                    'rq_jobs{queue="default",status="started"} 0.0',
                    'rq_jobs{queue="default",status="finished"} 0.0',
                    'rq_jobs{queue="default",status="failed"} 0.0',
                    'rq_jobs{queue="default",status="deferred"} 0.0',
                    'rq_jobs{queue="default",status="scheduled"} 0.0',
                    # worker information
                    '# HELP rq_workers RQ workers',
                    'rq_workers{name="test_worker",queues="default",state="?"} 1.0',
                    '# HELP rq_job_successful_total RQ successful job count',
                    'rq_job_successful_total{name="test_worker",queues="default"} 0.0',
                    '# HELP rq_job_failed_total RQ failed job count',
                    'rq_job_failed_total{name="test_worker",queues="default"} 0.0',
                    '# HELP rq_working_seconds_total RQ total working time',
                    'rq_working_seconds_total{name="test_worker",queues="default"} 0.0',
                }
            )

            worker.work(burst=True, max_jobs=4)
            self.assertMetricsContain(
                {
                    # job information
                    'rq_jobs{queue="default",status="queued"} 7.0',
                    'rq_jobs{queue="default",status="finished"} 3.0',
                    'rq_jobs{queue="default",status="failed"} 1.0',
                    # worker information
                    'rq_workers{name="test_worker",queues="default",state="idle"} 1.0',
                    'rq_job_successful_total{name="test_worker",queues="default"} 3.0',
                    'rq_job_failed_total{name="test_worker",queues="default"} 1.0',
                }
            )

            worker.work(burst=True)
            self.assertMetricsContain(
                {
                    # job information
                    'rq_jobs{queue="default",status="queued"} 0.0',
                    'rq_jobs{queue="default",status="finished"} 10.0',
                    'rq_jobs{queue="default",status="failed"} 1.0',
                    # worker information
                    'rq_workers{name="test_worker",queues="default",state="idle"} 1.0',
                    'rq_job_successful_total{name="test_worker",queues="default"} 10.0',
                    'rq_job_failed_total{name="test_worker",queues="default"} 1.0',
                }
            )
        finally:
            register_death()


@skipIf(prometheus_client is not None, 'prometheus_client is installed')
class NoPrometheusTest(TestCase):
    def test_no_metrics_without_prometheus_client(self):
        with self.assertRaises(NoReverseMatch):
            reverse('rq_metrics')
