"""
Standalone RQ Dashboard CLI.

Usage:
    rq-dashboard init                       # generate ./rq_dashboard_config.py
    rq-dashboard run                        # auto-detects ./rq_dashboard_config.py
    rq-dashboard run --config my_config.py
    rq-dashboard run --config my_config.py --host 0.0.0.0 --port 8080
    rq-dashboard createsuperuser            # add a superuser
    rq-dashboard changepassword <username>  # reset a password
"""

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

import django
from django.conf import settings
from django.core.management import call_command
from django.core.management.utils import get_random_secret_key

SAMPLE_CONFIG_FILENAME = 'rq_dashboard_config.py'

SAMPLE_CONFIG_TEMPLATE = '''\
"""Configuration for rq-dashboard. Edit the values below to match your setup.

NOTE: this file contains a SECRET_KEY used to sign sessions and admin cookies.
Treat it like a password — do NOT commit it to version control.
"""

SECRET_KEY = "__SECRET_KEY__"

RQ_QUEUES = {
    "default": {
        "URL": "redis://localhost:6379/0",
    },
    # Add as many queues as you want. Each entry can use a URL (recommended,
    # works with most hosted Redis providers) or explicit HOST/PORT/DB fields.
    #
    # "high": {
    #     "URL": "redis://:password@redis.example.com:6380/0",
    #     "SSL": True,
    # },
    # "low": {
    #     "HOST": "localhost",
    #     "PORT": 6379,
    #     "DB": 1,
    #     # "PASSWORD": "...",
    # },
}

# Optional settings — uncomment to use:
# DEBUG = True
# ALLOWED_HOSTS = ["dashboard.example.com"]  # default: ["127.0.0.1", "localhost"]
'''


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load RQ configuration from a Python file."""
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        sys.exit(f"Error: Config file not found: {config_path}")

    spec = importlib.util.spec_from_file_location("rq_config", config_path)
    if spec is None or spec.loader is None:
        sys.exit(f"Error: Could not load config file: {config_path}")

    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)

    if not hasattr(config_module, 'RQ_QUEUES'):
        sys.exit("Error: Config file must define RQ_QUEUES")

    if not hasattr(config_module, 'SECRET_KEY'):
        sys.exit(
            "Error: Config file must define SECRET_KEY. "
            "Run `rq-dashboard init` to generate a fresh config with a random key."
        )

    config = {
        'RQ_QUEUES': config_module.RQ_QUEUES,
        'SECRET_KEY': config_module.SECRET_KEY,
    }

    if hasattr(config_module, 'RQ'):
        config['RQ'] = config_module.RQ
    if hasattr(config_module, 'DEBUG'):
        config['DEBUG'] = config_module.DEBUG
    if hasattr(config_module, 'ALLOWED_HOSTS'):
        config['ALLOWED_HOSTS'] = config_module.ALLOWED_HOSTS

    return config


def resolve_config_path(explicit: Optional[str]) -> Path:
    """Resolve which config file to load."""
    if explicit:
        return Path(explicit)

    cwd_config = Path.cwd() / SAMPLE_CONFIG_FILENAME
    if cwd_config.exists():
        return cwd_config

    sys.exit(
        "rq-dashboard requires a config file.\n"
        "\n"
        f"It looks for `{SAMPLE_CONFIG_FILENAME}` in the current directory, "
        "or a path passed via `--config`.\n"
        "\n"
        "To generate a starter config in this directory, run: `rq-dashboard init`"
    )


def write_sample_config() -> None:
    """Write a starter rq_dashboard_config.py into the current directory."""
    path = Path.cwd() / SAMPLE_CONFIG_FILENAME
    if path.exists():
        sys.exit(f"{path} already exists. Refusing to overwrite.")

    body = SAMPLE_CONFIG_TEMPLATE.replace("__SECRET_KEY__", get_random_secret_key())
    path.write_text(body)
    print(f"Wrote {path}")
    print("Edit it to point at your Redis instance(s), then run `rq-dashboard run`.")


def configure_django(config: dict[str, Any], config_path: Path) -> None:
    """Configure Django settings programmatically."""
    state_dir = config_path.resolve().parent
    db_path = state_dir / 'rq_dashboard.sqlite3'

    debug = config.get('DEBUG', True)

    # Default to localhost only for security. Users can override in config
    # if they need to access the dashboard from other hosts.
    allowed_hosts = config.get('ALLOWED_HOSTS', ['127.0.0.1', 'localhost'])

    settings.configure(
        DEBUG=debug,
        ALLOWED_HOSTS=allowed_hosts,
        SECRET_KEY=config['SECRET_KEY'],
        ROOT_URLCONF='django_rq.dashboard.urls',
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.admin',
            'django.contrib.auth',
            'django.contrib.messages',
            'django.contrib.sessions',
            'django.contrib.staticfiles',
            'django_rq',
        ],
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(db_path),
            }
        },
        MIDDLEWARE=[
            'django.middleware.security.SecurityMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
        ],
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': [],
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.debug',
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                    ],
                },
            },
        ],
        STATIC_URL='/static/',
        STATIC_ROOT=str(state_dir / 'rq_dashboard_static'),
        RQ_QUEUES=config['RQ_QUEUES'],
        RQ=config.get('RQ', {}),
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        LOGIN_URL='/admin/login/',
        LOGIN_REDIRECT_URL='/',
    )

    django.setup()


def check_or_create_superuser() -> None:
    """Check if superuser exists, prompt to create one if not."""
    from django.contrib.auth import get_user_model
    from django.core.management.base import CommandError

    User = get_user_model()

    if User.objects.filter(is_superuser=True).exists():
        return

    print("=" * 70)
    print("No superuser found. You need to create one to access the dashboard.")
    print("=" * 70)
    print()

    try:
        call_command('createsuperuser', interactive=True)
        print()
        print("✓ Superuser created successfully!")
        print()
    except KeyboardInterrupt:
        print("\n\nSuperuser creation cancelled.")
        print("You need a superuser account to access the dashboard.")
        sys.exit(1)
    except CommandError as e:
        print(f"\n✗ Error creating superuser: {e}")
        print("\nPlease run the command again to retry.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        print("\nPlease run the command again to retry.")
        sys.exit(1)


def collect_static_files() -> None:
    """Collect static files if not in DEBUG mode."""
    if not settings.DEBUG:
        call_command('collectstatic', '--no-input', verbosity=0)


def run_server(host: str, port: int) -> None:
    """Run the Django development server."""
    print(f"Starting RQ Dashboard at http://{host}:{port}/")
    print("Log in with your superuser credentials.")
    print("Press Ctrl+C to stop.")
    print()

    # Use --insecure flag to serve static files even when DEBUG=False.
    # This is acceptable for a standalone dashboard tool.
    if settings.DEBUG:
        call_command('runserver', f'{host}:{port}', use_reloader=False)
    else:
        call_command('runserver', f'{host}:{port}', '--insecure', use_reloader=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='rq-dashboard',
        description='Run a standalone RQ Dashboard.',
    )
    subparsers = parser.add_subparsers(dest='command', metavar='<command>')

    subparsers.add_parser(
        'init',
        help=f'Generate a starter {SAMPLE_CONFIG_FILENAME} in the current directory.',
    )

    run_parser = subparsers.add_parser(
        'run',
        help='Start the dashboard server.',
    )
    run_parser.add_argument(
        '--config',
        '-c',
        help=(
            f'Path to a Python config file. Defaults to ./{SAMPLE_CONFIG_FILENAME} if present in the current directory.'
        ),
    )
    run_parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind the server to (default: 127.0.0.1)',
    )
    run_parser.add_argument(
        '--port',
        '-p',
        type=int,
        default=8000,
        help='Port to bind the server to (default: 8000)',
    )

    config_help = (
        f'Path to a Python config file. Defaults to ./{SAMPLE_CONFIG_FILENAME} if present in the current directory.'
    )

    create_parser = subparsers.add_parser(
        'createsuperuser',
        help='Create a new superuser (interactive).',
    )
    create_parser.add_argument('--config', '-c', help=config_help)

    password_parser = subparsers.add_parser(
        'changepassword',
        help="Change a user's password (interactive).",
    )
    password_parser.add_argument('username', help='Username whose password should be changed.')
    password_parser.add_argument('--config', '-c', help=config_help)

    return parser


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    return build_parser().parse_args(args)


def main() -> None:
    """Main entry point for the rq-dashboard CLI."""
    args = parse_args()

    if args.command is None:
        build_parser().print_help()
        sys.exit(0)

    if args.command == 'init':
        write_sample_config()
        return

    config_path = resolve_config_path(args.config)
    config = load_config(config_path)
    configure_django(config, config_path)
    call_command('migrate', verbosity=0)

    if args.command == 'createsuperuser':
        call_command('createsuperuser')
        return

    if args.command == 'changepassword':
        call_command('changepassword', args.username)
        return

    # args.command == 'run'
    collect_static_files()
    check_or_create_superuser()
    run_server(args.host, args.port)


if __name__ == '__main__':
    main()
