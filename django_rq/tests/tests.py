from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import TestCase
from django.utils.unittest import skipIf
from django.test.utils import override_settings
from django.conf import settings

from rq.job import Job

from django_rq.management.commands.rqworker import get_queues
from django_rq.queues import get_connection, get_queue

try:
    from rq_scheduler import Scheduler
    from .queues import get_scheduler
    RQ_SCHEDULER_INSTALLED = True
except ImportError:
    RQ_SCHEDULER_INSTALLED = False


QUEUES = settings.RQ_QUEUES


class DjangoRQTest(TestCase):

    def test_get_connection(self):
        """
        Test that get_connection returns the right connection based on
        settings.RQ_QUEUES
        """
        config = QUEUES['default']
        connection = get_connection()
        connection_kwargs = connection.connection_pool.connection_kwargs
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

        config = QUEUES['test']
        connection = get_connection('test')
        connection_kwargs = connection.connection_pool.connection_kwargs
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    def test_get_queue(self):
        # Test that get_queue use the right parameters for its connection
        config = QUEUES['default']
        queue = get_queue('default')
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, 'default')
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

        config = QUEUES['test']
        queue = get_queue('test')
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, 'test')
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    @override_settings(RQ_QUEUES=None)
    def test_empty_queue_setting_raises_exception(self):
        # Raise an exception if RQ_QUEUES is not defined
        self.assertRaises(ImproperlyConfigured, get_connection)

    def test_get_queues(self):
        # Getting queues with the same redis connection is ok
        self.assertEqual(get_queues('test', 'test2'), [get_queue('test'), get_queue('test2')])
        # Getting queues with different connections raises an exception
        self.assertRaises(ValueError, get_queues, 'default', 'test')

    @skipIf(RQ_SCHEDULER_INSTALLED is False, 'RQ Scheduler not installed')
    def test_get_scheduler(self):
        """
        Ensure get_scheduler creates a scheduler instance with the right
        connection params.
        """

        config = QUEUES['default']
        scheduler = get_scheduler()
        connection_kwargs = scheduler.connection.connection_pool.connection_kwargs
        self.assertEqual(scheduler.queue_name, 'default')
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

        config = QUEUES['test']
        scheduler = get_scheduler('test')
        connection_kwargs = scheduler.connection.connection_pool.connection_kwargs
        self.assertEqual(scheduler.queue_name, 'test')
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

