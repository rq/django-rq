"""
Cron configuration file #2 for testing the rqcron management command.
Contains different jobs for alternative test scenarios.
"""

from rq import cron

from .fixtures import say_hello

# Register a job with different arguments for testing
cron.register(say_hello, 'default', args=('from cron config2',), cron='*/2 * * * *')  # Every 2 minutes

# Register another job with a different interval
cron.register(say_hello, 'default', args=('every 10 seconds config2',), interval=10)
