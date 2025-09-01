"""
Cron configuration file #1 for testing the rqcron management command.
Contains 2 jobs for the main test.
"""
from rq import cron
from .fixtures import say_hello


# Register a simple cron job that runs every minute
cron.register(say_hello, 'default', args=('from cron config1',), cron='* * * * *')

# Register another job that runs every 5 seconds using interval
cron.register(say_hello, 'default', args=('every 5 seconds config1',), interval=5)