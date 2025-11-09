import sys
from unittest import mock, skipIf
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, override_settings

from django_rq.connection_utils import get_connection, get_redis_connection, get_unique_connection_configs
from django_rq.queues import get_queue
from django_rq.tests.fixtures import access_self

QUEUES = settings.RQ_QUEUES


@override_settings(RQ={'AUTOCOMMIT': True})
class ConnectionTest(TestCase):
    def setUp(self):
        """Used to test with / without sentry_sdk available."""
        self.mock_sdk = mock.MagicMock()
        self.mock_sdk.Hub.current.client.options = {}
        sys.modules["sentry_sdk"] = self.mock_sdk

    def tearDown(self):
        del sys.modules["sentry_sdk"]

    def test_get_connection_default(self):
        """
        Test that get_connection returns the right connection based for
        `default` queue.
        """
        config = QUEUES['default']
        connection = get_connection()
        connection_kwargs = connection.connection_pool.connection_kwargs
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    def test_get_connection_test(self):
        """
        Test that get_connection returns the right connection based for
        `test` queue.
        """
        config = QUEUES['test']
        connection = get_connection('test')
        connection_kwargs = connection.connection_pool.connection_kwargs
        self.assertEqual(connection_kwargs['host'], config['HOST'])
        self.assertEqual(connection_kwargs['port'], config['PORT'])
        self.assertEqual(connection_kwargs['db'], config['DB'])

    @patch('django_rq.connection_utils.Sentinel')
    def test_get_connection_sentinel(self, sentinel_class_mock):
        """
        Test that get_connection returns the right connection based for
        `sentinel` queue.
        """
        sentinel_mock = MagicMock()
        sentinel_mock.master_for.return_value = sentinel_mock
        sentinel_class_mock.side_effect = [sentinel_mock]

        config = QUEUES['sentinel']
        connection = get_connection('sentinel')

        self.assertEqual(connection, sentinel_mock)
        self.assertEqual(sentinel_mock.master_for.call_count, 1)
        self.assertEqual(sentinel_class_mock.call_count, 1)

        sentinel_instances = sentinel_class_mock.call_args[0][0]
        self.assertListEqual(config['SENTINELS'], sentinel_instances)

        connection_kwargs = sentinel_mock.master_for.call_args[1]
        self.assertEqual(connection_kwargs['service_name'], config['MASTER_NAME'])

    @patch('django_rq.connection_utils.Sentinel')
    def test_sentinel_class_initialized_with_kw_args(self, sentinel_class_mock):
        """
        Test that Sentinel object is initialized with proper connection kwargs.
        """
        config = {
            'SENTINELS': [],
            'MASTER_NAME': 'test_master',
            'SOCKET_TIMEOUT': 0.2,
            'DB': 0,
            'USERNAME': 'redis-user',
            'PASSWORD': 'redis-pass',
            'CONNECTION_KWARGS': {'ssl': False},
            'SENTINEL_KWARGS': {'username': 'sentinel-user', 'password': 'sentinel-pass', 'socket_timeout': 0.3},
        }
        get_redis_connection(config)
        sentinel_init_sentinel_kwargs = sentinel_class_mock.call_args[1]
        self.assertDictEqual(
            sentinel_init_sentinel_kwargs,
            {
                'db': 0,
                'username': 'redis-user',
                'password': 'redis-pass',
                'socket_timeout': 0.2,
                'ssl': False,
                'sentinel_kwargs': {'username': 'sentinel-user', 'password': 'sentinel-pass', 'socket_timeout': 0.3},
            },
        )

    def test_get_unique_connection_configs(self):
        connection_params_1 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        }
        connection_params_2 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 1,
        }
        config = {'default': connection_params_1, 'test': connection_params_2}
        unique_configs = get_unique_connection_configs(config)
        self.assertEqual(len(unique_configs), 2)
        self.assertIn(connection_params_1, unique_configs)
        self.assertIn(connection_params_2, unique_configs)

        # self.assertEqual(get_unique_connection_configs(config),
        #                  [connection_params_1, connection_params_2])
        config = {'default': connection_params_1, 'test': connection_params_1}
        # Should return one connection config since it filters out duplicates
        self.assertEqual(get_unique_connection_configs(config), [connection_params_1])

    def test_get_unique_connection_configs_with_different_timeout(self):
        connection_params_1 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        }
        connection_params_2 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 1,
        }
        queue_params_a = dict(connection_params_1)
        queue_params_b = dict(connection_params_2)
        queue_params_c = dict(connection_params_2)
        queue_params_c["DEFAULT_TIMEOUT"] = 1
        config = {
            'default': queue_params_a,
            'test_b': queue_params_b,
            'test_c': queue_params_c,
        }
        unique_configs = get_unique_connection_configs(config)
        self.assertEqual(len(unique_configs), 2)
        self.assertIn(connection_params_1, unique_configs)
        self.assertIn(connection_params_2, unique_configs)

    def test_get_unique_connection_configs_deterministic_order(self):
        """
        Test that get_unique_connection_configs returns configs in deterministic order
        based on sorted queue names, regardless of input dict key order.
        This allows using connection_index reliably.
        """
        import random

        connection_params_1 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        }
        connection_params_2 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 1,
        }
        connection_params_3 = {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 2,
        }

        # Test with duplicates: zebra and alpha share connection_params_1
        queue_items = [
            ('zebra', connection_params_3),
            ('alpha', connection_params_1),
            ('charlie', connection_params_2),
            ('delta', connection_params_1),  # duplicate of alpha
        ]

        results = []
        # Call get_unique_connection_configs 5 times with reshuffled key order
        for _ in range(5):
            # Reshuffle the order of items to prove ordering doesn't matter
            random.shuffle(queue_items)
            config = dict(queue_items)

            result = get_unique_connection_configs(config)
            results.append(result)

        # All results should be identical despite different input dict orderings
        first_result = results[0]
        for result in results:
            self.assertEqual(result, first_result)

        # Results should be in order based on sorted queue names
        # Sorted order: alpha (params_1), charlie (params_2), delta (params_1 dup), zebra (params_3)
        # Unique configs in order: params_1 (from alpha), params_2 (from charlie), params_3 (from zebra)
        self.assertEqual(first_result, [connection_params_1, connection_params_2, connection_params_3])


class RedisCacheTest(TestCase):
    @skipIf(settings.REDIS_CACHE_TYPE != 'django-redis', 'django-redis not installed')
    @patch('django_redis.get_redis_connection')
    def test_get_queue_django_redis(self, mocked):
        """
        Test that the USE_REDIS_CACHE option for configuration works.
        """
        queue = get_queue('django-redis')
        queue.enqueue(access_self)
        self.assertEqual(len(queue), 1)
        self.assertEqual(mocked.call_count, 1)

    @skipIf(settings.REDIS_CACHE_TYPE != 'django-redis-cache', 'django-redis-cache not installed')
    def test_get_queue_django_redis_cache(self):
        """
        Test that the USE_REDIS_CACHE option for configuration works.
        """
        queueName = 'django-redis-cache'
        queue = get_queue(queueName)
        connection_kwargs = queue.connection.connection_pool.connection_kwargs
        self.assertEqual(queue.name, queueName)

        cacheHost = settings.CACHES[queueName]['LOCATION'].split(':')[0]
        cachePort = settings.CACHES[queueName]['LOCATION'].split(':')[1]
        cacheDBNum = settings.CACHES[queueName]['OPTIONS']['DB']

        self.assertEqual(connection_kwargs['host'], cacheHost)
        self.assertEqual(connection_kwargs['port'], int(cachePort))
        self.assertEqual(connection_kwargs['db'], int(cacheDBNum))
        self.assertEqual(connection_kwargs['password'], None)
