"""
Tests for Django-RQ admin integration.

These tests verify that Django-RQ views are automatically accessible via Django admin
URLs without requiring manual URL configuration in urls.py.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.test.client import Client
from django.urls import reverse

from django_rq import get_queue

from .fixtures import say_hello
from .utils import get_queue_index


@override_settings(
    RQ={'AUTOCOMMIT': True},
    RQ_QUEUES={
        'default': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
            'DEFAULT_TIMEOUT': 500,
        }
    },
)
class AuthenticatedAdminURLTest(TestCase):
    """Test Django-RQ views accessible via Django admin URLs with authenticated user"""

    def setUp(self):
        self.client = Client()
        # Create superuser for admin access
        self.admin_user = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='admin123'
        )
        self.client.login(username='admin', password='admin123')

    def test_dashboard_url(self):
        """Verify dashboard accessible via admin URLs"""
        # Use admin changelist URL which proxies to stats view
        response = self.client.get(reverse('admin:django_rq_queue_changelist'))
        self.assertEqual(response.status_code, 200)
        # Should render the stats template
        self.assertTemplateUsed(response, 'django_rq/stats.html')

    def test_stats_json_url(self):
        """Verify stats JSON endpoint accessible via admin URLs"""
        response = self.client.get(reverse('rq_home_json'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_queue_jobs_url(self):
        """Verify queue jobs view accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(reverse('rq_jobs', args=[queue_index]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'django_rq/jobs.html')

    def test_workers_url(self):
        """Verify workers view accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(reverse('rq_workers', args=[queue_index]))
        self.assertEqual(response.status_code, 200)

    def test_job_detail_url(self):
        """Verify job detail view accessible via admin URLs"""
        queue = get_queue('default')
        job = queue.enqueue(say_hello)
        queue_index = get_queue_index('default')

        response = self.client.get(reverse('rq_job_detail', args=[queue_index, job.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'django_rq/job_detail.html')

    def test_failed_jobs_url(self):
        """Verify failed jobs registry accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(reverse('rq_failed_jobs', args=[queue_index]))
        self.assertEqual(response.status_code, 200)

    def test_finished_jobs_url(self):
        """Verify finished jobs registry accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(reverse('rq_finished_jobs', args=[queue_index]))
        self.assertEqual(response.status_code, 200)

    def test_scheduled_jobs_url(self):
        """Verify scheduled jobs registry accessible via admin URLs"""
        queue_index = get_queue_index('default')
        response = self.client.get(reverse('rq_scheduled_jobs', args=[queue_index]))
        self.assertEqual(response.status_code, 200)

    def test_url_names_still_work(self):
        """Verify reverse() with URL names still resolves correctly"""
        # Test that URL names can be resolved
        # Note: When accessed via admin, URLs may need admin namespace
        try:
            url = reverse('rq_home')
            self.assertTrue(url.startswith('/'))
        except Exception:
            # If standard reverse fails, try with admin namespace
            url = reverse('admin:rq_home')
            self.assertTrue(url.startswith('/admin/'))


@override_settings(
    RQ={'AUTOCOMMIT': True},
    RQ_QUEUES={
        'default': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
            'DEFAULT_TIMEOUT': 500,
        }
    },
)
class UnauthenticatedAdminURLTest(TestCase):
    """Test Django-RQ views accessible via Django admin URLs without authentication"""

    def setUp(self):
        self.client = Client()

    def test_requires_staff_authentication(self):
        """Verify admin views require staff user authentication"""
        url = reverse('admin:django_rq_queue_changelist')

        # Test 1: Unauthenticated access should redirect to login
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

        # Test 2: Non-staff user should be denied access
        regular_user = User.objects.create_user(username='regular', password='pass')
        regular_user.is_active = True
        regular_user.save()

        self.client.login(username='regular', password='pass')
        response = self.client.get(url)
        # Should redirect to login page or show permission error
        self.assertIn(response.status_code, [302, 403])

    @override_settings(RQ_API_TOKEN='12345abcde')
    def test_api_token_authentication(self):
        """Verify API token authentication works through admin URLs"""
        token = '12345abcde'
        # Test 1: Valid token should succeed
        response = self.client.get(reverse('rq_home_json'), HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertIn('queues', data)

        # Test 2: Missing token should fail
        response = self.client.get(reverse('rq_home_json'))
        self.assertEqual(response.status_code, 401)

        # Test 3: Invalid token should fail
        response = self.client.get(reverse('rq_home_json'), HTTP_AUTHORIZATION='Bearer wrong_token')
        self.assertEqual(response.status_code, 401)
