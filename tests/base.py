from typing import Any

from django.test import TestCase
from redis import Redis


class DjangoRQTestCase(TestCase):
    """Base test case for django-rq tests with common assertion helpers."""

    def assert_connection_kwargs(self, connection: Redis, expected_config: dict[str, Any]) -> None:
        """
        Assert that connection pool kwargs match expected configuration.

        Args:
            connection: Redis connection object
            expected_config: Dict with config keys (either HOST/PORT/DB or lowercase equivalents)

        Examples:
            # With settings-based config (HOST/PORT/DB keys)
            config = QUEUES['default']
            queue = get_queue('default')
            self.assert_connection_kwargs(queue.connection, config)

            # With explicit kwargs
            self.assert_connection_kwargs(connection, {
                'host': 'localhost',
                'port': 6379,
                'db': 0
            })
        """
        connection_kwargs = connection.connection_pool.connection_kwargs

        # If expected_config has HOST/PORT/DB keys (from settings.RQ_QUEUES)
        if 'HOST' in expected_config:
            self.assertEqual(connection_kwargs['host'], expected_config['HOST'])
            self.assertEqual(connection_kwargs['port'], expected_config['PORT'])
            self.assertEqual(connection_kwargs['db'], expected_config.get('DB', 0))
        else:
            # Direct comparison for explicit kwargs
            for key, value in expected_config.items():
                self.assertEqual(connection_kwargs[key], value)
