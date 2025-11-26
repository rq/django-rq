"""Tests for the standalone RQ Dashboard CLI."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestLoadConfig(unittest.TestCase):
    """Tests for the load_config function."""

    def test_load_valid_config(self):
        """Test loading a valid config file."""
        # Import here to avoid Django setup issues
        from django_rq.dashboard.cli import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
RQ_QUEUES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
    }
}
""")
            f.flush()
            config_path = f.name

        try:
            config = load_config(config_path)
            self.assertIn('RQ_QUEUES', config)
            self.assertEqual(config['RQ_QUEUES']['default']['HOST'], 'localhost')
        finally:
            os.unlink(config_path)

    def test_load_config_with_optional_settings(self):
        """Test loading a config file with optional RQ settings."""
        from django_rq.dashboard.cli import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
RQ_QUEUES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
    }
}
RQ = {
    'AUTOCOMMIT': True,
}
SECRET_KEY = 'my-secret-key'
""")
            f.flush()
            config_path = f.name

        try:
            config = load_config(config_path)
            self.assertIn('RQ', config)
            self.assertEqual(config['RQ']['AUTOCOMMIT'], True)
            self.assertEqual(config['SECRET_KEY'], 'my-secret-key')
        finally:
            os.unlink(config_path)

    def test_load_config_missing_file(self):
        """Test loading a non-existent config file."""
        from django_rq.dashboard.cli import load_config

        with self.assertRaises(SystemExit):
            load_config('/nonexistent/path/config.py')

    def test_load_config_missing_rq_queues(self):
        """Test loading a config file without RQ_QUEUES."""
        from django_rq.dashboard.cli import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("FOO = 'bar'\n")
            f.flush()
            config_path = f.name

        try:
            with self.assertRaises(SystemExit):
                load_config(config_path)
        finally:
            os.unlink(config_path)


class TestSecretKey(unittest.TestCase):
    """Tests for secret key generation."""

    def test_get_or_create_secret_key_creates_new(self):
        """Test that a new secret key is created if none exists."""
        from django_rq.dashboard.cli import get_or_create_secret_key, DASHBOARD_DIR

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('django_rq.dashboard.cli.DASHBOARD_DIR', Path(tmpdir) / '.rqdashboard'):
                secret_key = get_or_create_secret_key()
                self.assertTrue(len(secret_key) > 20)

                # Second call should return the same key
                secret_key2 = get_or_create_secret_key()
                self.assertEqual(secret_key, secret_key2)


class TestMainArgParser(unittest.TestCase):
    """Tests for the main argument parser."""

    def test_argparser_requires_config(self):
        """Test that --config is required."""
        from django_rq.dashboard.cli import main

        with patch('sys.argv', ['rqdashboard']):
            with self.assertRaises(SystemExit):
                main()

    def test_argparser_accepts_all_options(self):
        """Test that all options are accepted."""
        import argparse
        from django_rq.dashboard.cli import main

        # We can't easily test the full main() without mocking everything,
        # but we can at least verify the argparser accepts the options
        with patch('sys.argv', ['rqdashboard', '--config', 'test.py', '--host', '0.0.0.0', '--port', '9000']):
            with patch('django_rq.dashboard.cli.load_config') as mock_load:
                with patch('django_rq.dashboard.cli.configure_django'):
                    with patch('django_rq.dashboard.cli.run_migrations'):
                        with patch('django_rq.dashboard.cli.check_or_create_superuser'):
                            with patch('django_rq.dashboard.cli.run_server') as mock_run:
                                mock_load.return_value = {'RQ_QUEUES': {}}
                                main()
                                mock_run.assert_called_once_with('0.0.0.0', 9000)


class TestURLConfiguration(unittest.TestCase):
    """Tests for the dashboard URL configuration."""

    def test_url_namespace_registration(self):
        """Test that django_rq_dashboard namespace is properly registered in dashboard URLs."""
        from django.test import override_settings
        from django.urls import clear_url_caches, reverse

        # Test with dashboard_urls (which uses include() with explicit namespace)
        with override_settings(ROOT_URLCONF='django_rq.dashboard.urls'):
            clear_url_caches()

            # Test that namespaced URLs can be reversed with django_rq_dashboard namespace
            url = reverse('django_rq_dashboard:rq_home')
            self.assertEqual(url, '/')

            url = reverse('django_rq_dashboard:rq_jobs', kwargs={'queue_index': 0})
            self.assertEqual(url, '/queues/0/')

            url = reverse('django_rq_dashboard:rq_failed_jobs', kwargs={'queue_index': 0})
            self.assertEqual(url, '/queues/0/failed/')

            # Test admin namespace
            url = reverse('admin:index')
            self.assertEqual(url, '/admin/')

    def test_url_resolution(self):
        """Test that URLs resolve correctly in dashboard URLs."""
        from django.test import override_settings
        from django.urls import clear_url_caches, resolve

        # Test with dashboard_urls
        with override_settings(ROOT_URLCONF='django_rq.dashboard.urls'):
            clear_url_caches()

            # Test URL resolution uses django_rq_dashboard namespace
            match = resolve('/')
            self.assertEqual(match.view_name, 'django_rq_dashboard:rq_home')

            match = resolve('/queues/0/')
            self.assertEqual(match.view_name, 'django_rq_dashboard:rq_jobs')

            match = resolve('/admin/')
            self.assertEqual(match.view_name, 'admin:index')
