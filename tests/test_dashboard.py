"""Tests for the standalone RQ Dashboard CLI."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


VALID_CONFIG_BODY = """
SECRET_KEY = 'test-secret-key'
RQ_QUEUES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
    }
}
"""


class TestLoadConfig(unittest.TestCase):
    """Tests for the load_config function."""

    def test_load_valid_config(self):
        from django_rq.dashboard.cli import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(VALID_CONFIG_BODY)
            f.flush()
            config_path = f.name

        try:
            config = load_config(config_path)
            self.assertIn('RQ_QUEUES', config)
            self.assertEqual(config['RQ_QUEUES']['default']['HOST'], 'localhost')
            self.assertEqual(config['SECRET_KEY'], 'test-secret-key')
        finally:
            os.unlink(config_path)

    def test_load_config_with_optional_settings(self):
        from django_rq.dashboard.cli import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(VALID_CONFIG_BODY)
            f.write("RQ = {'COMMIT_MODE': 'auto'}\n")
            f.write("DEBUG = False\n")
            f.write("ALLOWED_HOSTS = ['example.com']\n")
            f.flush()
            config_path = f.name

        try:
            config = load_config(config_path)
            self.assertEqual(config['RQ']['COMMIT_MODE'], 'auto')
            self.assertFalse(config['DEBUG'])
            self.assertEqual(config['ALLOWED_HOSTS'], ['example.com'])
        finally:
            os.unlink(config_path)

    def test_load_config_missing_file(self):
        from django_rq.dashboard.cli import load_config

        with self.assertRaises(SystemExit):
            load_config('/nonexistent/path/config.py')

    def test_load_config_missing_rq_queues(self):
        from django_rq.dashboard.cli import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("SECRET_KEY = 'x'\n")
            f.flush()
            config_path = f.name

        try:
            with self.assertRaises(SystemExit):
                load_config(config_path)
        finally:
            os.unlink(config_path)

    def test_load_config_missing_secret_key(self):
        from django_rq.dashboard.cli import load_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("RQ_QUEUES = {'default': {'HOST': 'localhost', 'PORT': 6379, 'DB': 0}}\n")
            f.flush()
            config_path = f.name

        try:
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stderr):
                with self.assertRaises(SystemExit):
                    load_config(config_path)
            self.assertIn('SECRET_KEY', stderr.getvalue())
        finally:
            os.unlink(config_path)


class TestParseArgs(unittest.TestCase):
    """Tests for the argument parser."""

    def test_no_subcommand(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args([])
        self.assertIsNone(args.command)

    def test_init_subcommand(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['init'])
        self.assertEqual(args.command, 'init')

    def test_run_with_all_options(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['run', '--config', 'test.py', '--host', '0.0.0.0', '--port', '9000'])

        self.assertEqual(args.command, 'run')
        self.assertEqual(args.config, 'test.py')
        self.assertEqual(args.host, '0.0.0.0')
        self.assertEqual(args.port, 9000)

    def test_run_with_short_options(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['run', '-c', 'config.py', '-p', '8080'])

        self.assertEqual(args.command, 'run')
        self.assertEqual(args.config, 'config.py')
        self.assertEqual(args.port, 8080)

    def test_run_defaults(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['run'])

        self.assertEqual(args.command, 'run')
        self.assertIsNone(args.config)
        self.assertEqual(args.host, '127.0.0.1')
        self.assertEqual(args.port, 8000)

    def test_bare_config_rejected(self):
        """`rq-dashboard --config x.py` (no `run` subcommand) is a parser error."""
        from django_rq.dashboard.cli import parse_args

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(['--config', 'x.py'])

    def test_main_with_no_args_prints_help_and_exits_zero(self):
        from django_rq.dashboard import cli

        stdout = io.StringIO()
        with patch.object(sys, 'argv', ['rq-dashboard']):
            with contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as exc:
                    cli.main()

        self.assertEqual(exc.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn('init', output)
        self.assertIn('run', output)
        self.assertIn('createsuperuser', output)
        self.assertIn('changepassword', output)

    def test_createsuperuser(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['createsuperuser'])

        self.assertEqual(args.command, 'createsuperuser')
        self.assertIsNone(args.config)

    def test_createsuperuser_with_config(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['createsuperuser', '--config', 'x.py'])

        self.assertEqual(args.command, 'createsuperuser')
        self.assertEqual(args.config, 'x.py')

    def test_changepassword_requires_username(self):
        from django_rq.dashboard.cli import parse_args

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(['changepassword'])

    def test_changepassword_with_username(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['changepassword', 'alice'])

        self.assertEqual(args.command, 'changepassword')
        self.assertEqual(args.username, 'alice')
        self.assertIsNone(args.config)

    def test_changepassword_with_username_and_config(self):
        from django_rq.dashboard.cli import parse_args

        args = parse_args(['changepassword', 'alice', '--config', 'x.py'])

        self.assertEqual(args.username, 'alice')
        self.assertEqual(args.config, 'x.py')


class TestInit(unittest.TestCase):
    """Tests for the `init` subcommand."""

    def _run_init_in(self, tmpdir):
        from django_rq.dashboard.cli import write_sample_config

        original = Path.cwd()
        os.chdir(tmpdir)
        try:
            write_sample_config()
        finally:
            os.chdir(original)

    def test_init_writes_config_with_secret_key(self):
        from django_rq.dashboard.cli import SAMPLE_CONFIG_FILENAME

        with tempfile.TemporaryDirectory() as tmpdir:
            with contextlib.redirect_stdout(io.StringIO()):
                self._run_init_in(tmpdir)

            written = Path(tmpdir) / SAMPLE_CONFIG_FILENAME
            self.assertTrue(written.exists())
            body = written.read_text()
            self.assertIn('RQ_QUEUES', body)
            self.assertIn('SECRET_KEY', body)
            self.assertNotIn('__SECRET_KEY__', body)

    def test_init_generates_unique_secret_keys(self):
        from django_rq.dashboard.cli import SAMPLE_CONFIG_FILENAME

        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with contextlib.redirect_stdout(io.StringIO()):
                self._run_init_in(a)
                self._run_init_in(b)

            body_a = (Path(a) / SAMPLE_CONFIG_FILENAME).read_text()
            body_b = (Path(b) / SAMPLE_CONFIG_FILENAME).read_text()
            self.assertNotEqual(body_a, body_b)

    def test_init_refuses_to_overwrite(self):
        from django_rq.dashboard.cli import SAMPLE_CONFIG_FILENAME

        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / SAMPLE_CONFIG_FILENAME
            existing.write_text("# pre-existing user file\n")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit):
                    self._run_init_in(tmpdir)

            self.assertIn("already exists", stdout.getvalue())
            self.assertEqual(existing.read_text(), "# pre-existing user file\n")


class TestResolveConfigPath(unittest.TestCase):
    """Tests for the config-path resolution helper."""

    def test_explicit_wins(self):
        from django_rq.dashboard.cli import resolve_config_path

        path = resolve_config_path('/some/explicit/path.py')
        self.assertEqual(path, Path('/some/explicit/path.py'))

    def test_picks_up_cwd_config(self):
        from django_rq.dashboard.cli import SAMPLE_CONFIG_FILENAME, resolve_config_path

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / SAMPLE_CONFIG_FILENAME).write_text("# placeholder\n")

            original = Path.cwd()
            os.chdir(tmpdir)
            try:
                path = resolve_config_path(None)
            finally:
                os.chdir(original)

            self.assertEqual(path.name, SAMPLE_CONFIG_FILENAME)
            self.assertEqual(path.parent.resolve(), Path(tmpdir).resolve())

    def test_no_config_exits_with_helpful_message(self):
        from django_rq.dashboard.cli import resolve_config_path

        with tempfile.TemporaryDirectory() as tmpdir:
            original = Path.cwd()
            os.chdir(tmpdir)
            try:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    with self.assertRaises(SystemExit):
                        resolve_config_path(None)
            finally:
                os.chdir(original)

            output = stdout.getvalue()
            self.assertIn("requires a config file", output)
            self.assertIn("rq-dashboard init", output)


class TestPassthroughDispatch(unittest.TestCase):
    """`createsuperuser` / `changepassword` dispatch via call_command."""

    def _run_main(self, argv):
        from django_rq.dashboard import cli

        with patch.object(sys, 'argv', argv), \
             patch.object(cli, 'resolve_config_path', return_value=Path('/fake/rq_dashboard_config.py')), \
             patch.object(cli, 'load_config', return_value={'RQ_QUEUES': {}, 'SECRET_KEY': 'x'}), \
             patch.object(cli, 'configure_django'), \
             patch.object(cli, 'call_command') as call_cmd:
            cli.main()
        return call_cmd

    def test_createsuperuser_invokes_call_command(self):
        call_cmd = self._run_main(['rq-dashboard', 'createsuperuser'])
        # First call is migrate; second is createsuperuser.
        self.assertEqual(call_cmd.call_args_list[0].args, ('migrate',))
        self.assertEqual(call_cmd.call_args_list[1].args, ('createsuperuser',))

    def test_changepassword_passes_username(self):
        call_cmd = self._run_main(['rq-dashboard', 'changepassword', 'alice'])
        self.assertEqual(call_cmd.call_args_list[0].args, ('migrate',))
        self.assertEqual(call_cmd.call_args_list[1].args, ('changepassword', 'alice'))


class TestURLConfiguration(unittest.TestCase):
    """Tests for the dashboard URL configuration."""

    def test_url_namespace_registration(self):
        """Test that django_rq URLs are registered under the django_rq namespace in dashboard URLs."""
        from django.test import override_settings
        from django.urls import clear_url_caches, reverse

        with override_settings(ROOT_URLCONF='django_rq.dashboard.urls'):
            clear_url_caches()

            url = reverse('django_rq:home')
            self.assertEqual(url, '/')

            url = reverse('django_rq:jobs', kwargs={'queue_index': 0})
            self.assertEqual(url, '/queues/0/')

            url = reverse('django_rq:failed_jobs', kwargs={'queue_index': 0})
            self.assertEqual(url, '/queues/0/failed/')

            url = reverse('admin:index')
            self.assertEqual(url, '/admin/')
