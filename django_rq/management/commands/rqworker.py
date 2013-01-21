import logging
from optparse import make_option

from django.core.management.base import BaseCommand

from redis.exceptions import ConnectionError

from django_rq.workers import get_worker

from rq import use_connection


# Setup logging for RQWorker if not already configured
logger = logging.getLogger('rq.worker')
if not logger.handlers:
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,

        "formatters": {
            "rq_console": {
                "format": "%(asctime)s %(message)s",
                "datefmt": "%H:%M:%S",
            },
        },

        "handlers": {
            "rq_console": {
                "level": "DEBUG",
                #"class": "logging.StreamHandler",
                "class": "rq.utils.ColorizingStreamHandler",
                "formatter": "rq_console",
                "exclude": ["%(asctime)s"],
            },
        },

        "worker": {
            "handlers": ["rq_console"],
            "level": "DEBUG" 
        }
    })


class Command(BaseCommand):
    """
    Runs RQ workers on specified queues. Note that all queues passed into a
    single rqworker command must share the same connection.

    Example usage:
    python manage.py rqworker high medium low
    """
    option_list = BaseCommand.option_list + (
        make_option(
            '--burst',
            action='store_true',
            dest='burst',
            default=False,
            help='Run worker in burst mode'
        ),
    )
    args = '<queue queue ...>'

    def handle(self, *args, **options):
        
        try:
            w = get_worker(*args)
            # Call use_connection to push the redis connection into LocalStack
            # without this, jobs using RQ's get_current_job() will fail
            use_connection(w.connection)
            w.work(burst=options.get('burst', False))
        except ConnectionError as e:
            print(e)
