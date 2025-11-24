#!/usr/bin/env python
"""
Standalone RQ Dashboard CLI.

Usage:
    rqdashboard --config my_config.py
    rqdashboard --config my_config.py --host 0.0.0.0 --port 8080
    rqdashboard --config my_config.py --create-user admin
"""
import argparse
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

# Dashboard data directory
DASHBOARD_DIR = Path.home() / '.rqdashboard'


def load_config(config_path: str) -> dict[str, Any]:
    """Load RQ configuration from a Python file."""
    config_path = os.path.abspath(config_path)
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("rq_config", config_path)
    if spec is None or spec.loader is None:
        print(f"Error: Could not load config file: {config_path}")
        sys.exit(1)

    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)

    if not hasattr(config_module, 'RQ_QUEUES'):
        print("Error: Config file must define RQ_QUEUES")
        sys.exit(1)

    config = {
        'RQ_QUEUES': config_module.RQ_QUEUES,
    }

    # Optional settings
    if hasattr(config_module, 'RQ'):
        config['RQ'] = config_module.RQ
    if hasattr(config_module, 'SECRET_KEY'):
        config['SECRET_KEY'] = config_module.SECRET_KEY

    return config


def get_or_create_secret_key() -> str:
    """Get or create a persistent secret key."""
    secret_key_file = DASHBOARD_DIR / 'secret_key'
    if secret_key_file.exists():
        return secret_key_file.read_text().strip()

    from django.core.management.utils import get_random_secret_key
    secret_key = get_random_secret_key()
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    secret_key_file.write_text(secret_key)
    return secret_key


def configure_django(config: dict[str, Any]) -> None:
    """Configure Django settings programmatically."""
    import django
    from django.conf import settings

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    db_path = DASHBOARD_DIR / 'db.sqlite3'

    secret_key = config.get('SECRET_KEY') or get_or_create_secret_key()

    settings.configure(
        DEBUG=True,
        SECRET_KEY=secret_key,
        ROOT_URLCONF='django_rq.dashboard_urls',
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
        RQ_QUEUES=config['RQ_QUEUES'],
        RQ=config.get('RQ', {}),
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        LOGIN_URL='/admin/login/',
    )

    django.setup()


def run_migrations() -> None:
    """Run database migrations."""
    from django.core.management import call_command
    call_command('migrate', '--run-syncdb', verbosity=0)


def check_or_create_superuser(create_user: str | None = None, password: str | None = None) -> None:
    """Check if superuser exists, prompt to create one if not."""
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    User = get_user_model()

    if create_user:
        # Create user with specified username
        if User.objects.filter(username=create_user).exists():
            print(f"User '{create_user}' already exists.")
            return

        if password:
            # Non-interactive mode using environment variable
            os.environ['DJANGO_SUPERUSER_PASSWORD'] = password
            call_command('createsuperuser', username=create_user, email='', interactive=False, verbosity=1)
            return

        # Interactive mode - let Django handle password prompts
        call_command('createsuperuser', username=create_user, email='', interactive=True)
        return

    # Check if any superuser exists
    if User.objects.filter(is_superuser=True).exists():
        return

    # Prompt to create superuser
    print("No superuser found. Let's create one to access the dashboard.")
    print()
    call_command('createsuperuser')


def run_server(host: str, port: int) -> None:
    """Run the Django development server."""
    from django.core.management import call_command
    print(f"Starting RQ Dashboard at http://{host}:{port}/")
    print("Log in with your superuser credentials.")
    print("Press Ctrl+C to stop.")
    print()
    call_command('runserver', f'{host}:{port}', use_reloader=False)


def main() -> None:
    """Main entry point for the rqdashboard CLI."""
    parser = argparse.ArgumentParser(
        description='Run a standalone RQ Dashboard',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example config file (my_config.py):

    RQ_QUEUES = {
        'default': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        },
        'high': {
            'URL': 'redis://localhost:6379/1',
        }
    }
""",
    )
    parser.add_argument(
        '--config', '-c',
        required=True,
        help='Path to Python config file containing RQ_QUEUES',
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind the server to (default: 127.0.0.1)',
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8000,
        help='Port to bind the server to (default: 8000)',
    )
    parser.add_argument(
        '--create-user',
        metavar='USERNAME',
        help='Create a superuser with the specified username',
    )
    parser.add_argument(
        '--password',
        help='Password for the superuser (use with --create-user for non-interactive setup)',
    )

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Configure Django
    configure_django(config)

    # Run migrations
    run_migrations()

    # Check/create superuser
    check_or_create_superuser(args.create_user, args.password)

    # Run server
    run_server(args.host, args.port)


if __name__ == '__main__':
    main()
