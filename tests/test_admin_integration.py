"""
Tests for Django-RQ admin integration.

These tests verify that Django-RQ views are automatically accessible via Django admin
URLs without requiring manual URL configuration in urls.py.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.test.client import Client
from django.urls import reverse

from django_rq import get_queue

from .fixtures import access_self
from .utils import get_queue_index


@override_settings(
    RQ={'AUTOCOMMIT': True},
    RQ_QUEUES={
        'default': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
            'DEFAULT_TIMEOUT': 500,
        },
        'django_rq_test': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        },
    },
)
class AdminURLIntegrationTest(TestCase):
    """Test Django-RQ views accessible via Django admin URLs"""

    def setUp(self):
        self.client = Client()
        # Create superuser for admin access
        self.admin_user = User.objects.create_superuser(username='admin', email='admin@example.com', password='admin123')
        self.client.login(username='admin', password='admin123')
        get_queue('django_rq_test').connection.flushall()

    def test_dashboard_url(self):
        """Verify dashboard accessible via admin URLs"""
        response = self.client.get('/admin/django_rq/queue/')
        self.assertEqual(response.status_code, 200)
        # Should render the stats template
        self.assertTemplateUsed(response, 'django_rq/stats.html')

    def test_stats_json_url(self):
        """Verify stats JSON endpoint accessible via admin URLs"""
        response = self.client.get('/admin/django_rq/queue/stats.json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_queue_jobs_url(self):
        """Verify queue jobs view accessible via admin URLs"""
        queue = get_queue('default')
        queue.enqueue(access_self)
        queue_index = get_queue_index('default')

        response = self.client.get(f'/admin/django_rq/queue/queues/{queue_index}/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'django_rq/jobs.html')

    def test_workers_url(self):
        """Verify workers view accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(f'/admin/django_rq/queue/workers/{queue_index}/')
        self.assertEqual(response.status_code, 200)

    def test_job_detail_url(self):
        """Verify job detail view accessible via admin URLs"""
        queue = get_queue('default')
        job = queue.enqueue(access_self)
        queue_index = get_queue_index('default')

        response = self.client.get(f'/admin/django_rq/queue/queues/{queue_index}/{job.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'django_rq/job_detail.html')

    def test_failed_jobs_url(self):
        """Verify failed jobs registry accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(f'/admin/django_rq/queue/queues/{queue_index}/failed/')
        self.assertEqual(response.status_code, 200)

    def test_finished_jobs_url(self):
        """Verify finished jobs registry accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(f'/admin/django_rq/queue/queues/{queue_index}/finished/')
        self.assertEqual(response.status_code, 200)

    def test_scheduled_jobs_url(self):
        """Verify scheduled jobs registry accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(f'/admin/django_rq/queue/queues/{queue_index}/scheduled/')
        self.assertEqual(response.status_code, 200)

    def test_requires_staff_authentication(self):
        """Verify admin views require staff user authentication"""
        # Test 1: Unauthenticated access should redirect to login
        self.client.logout()
        response = self.client.get('/admin/django_rq/queue/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

        # Test 2: Non-staff user should be denied access
        regular_user = User.objects.create_user(username='regular', password='pass')
        regular_user.is_active = True
        regular_user.save()

        self.client.login(username='regular', password='pass')
        response = self.client.get('/admin/django_rq/queue/')
        # Should redirect to login page or show permission error
        self.assertIn(response.status_code, [302, 403])

    def test_url_names_still_work(self):
        """Verify reverse() with URL names still resolves correctly"""
        queue_index = get_queue_index('default')

        # Test that URL names can be resolved
        # Note: When accessed via admin, URLs may need admin namespace
        try:
            url = reverse('rq_home')
            self.assertTrue(url.startswith('/'))
        except Exception:
            # If standard reverse fails, try with admin namespace
            url = reverse('admin:rq_home')
            self.assertTrue(url.startswith('/admin/'))

    @override_settings(RQ_API_TOKEN='12345abcde')
    def test_api_token_authentication(self):
        """Verify API token authentication works through admin URLs"""
        # Logout to test token-only auth
        self.client.logout()

        token = '12345abcde'
        # Patch API_TOKEN in stats_views since it's imported at module level
        with patch('django_rq.stats_views.API_TOKEN', token):
            # Test with Bearer token in headers
            response = self.client.get('/admin/django_rq/queue/stats.json', HTTP_AUTHORIZATION=f'Bearer {token}')
            # Should return 200 with stats, not redirect to login
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')

            # Verify it's actual stats, not an error
            import json

            data = json.loads(response.content.decode())
            self.assertNotIn('error', data)
            self.assertIn('queues', data)
