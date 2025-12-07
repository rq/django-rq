"""Tests for the standalone RQ Dashboard CLI."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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
    'COMMIT_MODE': 'auto',
}
SECRET_KEY = 'my-secret-key'
""")
            f.flush()
            config_path = f.name

        try:
            config = load_config(config_path)
            self.assertIn('RQ', config)
            self.assertEqual(config['RQ']['COMMIT_MODE'], 'auto')
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
        from django_rq.dashboard.cli import get_or_create_secret_key

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('django_rq.dashboard.cli.DASHBOARD_DIR', Path(tmpdir) / '.rqdashboard'):
                secret_key = get_or_create_secret_key()
                self.assertTrue(len(secret_key) > 20)

                # Second call should return the same key
                secret_key2 = get_or_create_secret_key()
                self.assertEqual(secret_key, secret_key2)


class TestParseArgs(unittest.TestCase):
    """Tests for the argument parser."""

    def test_config_is_required(self):
        """Test that --config is required."""
        from django_rq.dashboard.cli import parse_args

        with self.assertRaises(SystemExit):
            parse_args([])

    def test_parse_args_with_all_options(self):
        """Test that all options are correctly parsed."""
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['--config', 'test.py', '--host', '0.0.0.0', '--port', '9000'])

        self.assertEqual(args.config, 'test.py')
        self.assertEqual(args.host, '0.0.0.0')
        self.assertEqual(args.port, 9000)

    def test_parse_args_with_short_options(self):
        """Test that short options (-c, -p) work correctly."""
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['-c', 'config.py', '-p', '8080'])

        self.assertEqual(args.config, 'config.py')
        self.assertEqual(args.port, 8080)

    def test_parse_args_defaults(self):
        """Test default values for host and port."""
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['--config', 'test.py'])

        self.assertEqual(args.host, '127.0.0.1')
        self.assertEqual(args.port, 8000)


class TestURLConfiguration(unittest.TestCase):
    """Tests for the dashboard URL configuration."""

    def test_url_namespace_registration(self):
        """Test that django_rq URLs are properly registered in dashboard URLs."""
        from django.test import override_settings
        from django.urls import clear_url_caches, reverse

        # Test with dashboard_urls (which includes django_rq URLs directly)
        with override_settings(ROOT_URLCONF='django_rq.dashboard.urls'):
            clear_url_caches()

            # Test that URLs can be reversed without namespace
            url = reverse('rq_home')
            self.assertEqual(url, '/')

            url = reverse('rq_jobs', kwargs={'queue_index': 0})
            self.assertEqual(url, '/queues/0/')

            url = reverse('rq_failed_jobs', kwargs={'queue_index': 0})
            self.assertEqual(url, '/queues/0/failed/')

            # Test admin namespace
            url = reverse('admin:index')
            self.assertEqual(url, '/admin/')
