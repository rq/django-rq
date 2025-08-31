import logging
import sys

from django.core.management.base import BaseCommand

from ...cron import DjangoCronScheduler


class Command(BaseCommand):
    """
    Starts the RQ cron scheduler with Django-RQ integration.
    
    Example usage:
    python manage.py rqcron cron_config.py
    python manage.py rqcron myapp.cron_jobs --logging-level DEBUG
    """
    
    help = "Starts the RQ cron scheduler"
    
    def add_arguments(self, parser):
        # Positional argument for config file/module
        parser.add_argument(
            'config_path',
            help='Path to cron configuration file or module path'
        )
        
        # Optional logging level
        parser.add_argument(
            '--logging-level', '-l',
            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            default='INFO',
            help='Set logging level (default: INFO)'
        )

    def handle(self, *args, **options):
        """Main command handler."""
        config_path = options['config_path']
        logging_level = getattr(logging, options['logging_level'])
        
        # Create Django cron scheduler
        scheduler = DjangoCronScheduler(logging_level=logging_level)
        
        try:
            # Load configuration from file
            self.stdout.write(f'Loading cron configuration from {config_path}')
            scheduler.load_config_from_file(config_path)
            
            # Start the scheduler
            job_count = len(scheduler.get_jobs())
            self.stdout.write(
                self.style.SUCCESS(f'Starting cron scheduler with {job_count} jobs...')
            )
            
            scheduler.start()
            
        except FileNotFoundError:
            self.stderr.write(
                self.style.ERROR(f"Configuration file not found: '{config_path}'")
            )
            sys.exit(1)
        except ImportError as e:
            self.stderr.write(
                self.style.ERROR(f"Failed to import configuration: {e}")
            )
            sys.exit(1)
        except KeyboardInterrupt:
            self.stdout.write('\nShutting down cron scheduler...')
            sys.exit(0)
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"Error starting cron scheduler: {e}")
            )
            sys.exit(1)