import sys
from unittest import mock, skipIf
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from redis import Redis
from redis.connection import Connection, ConnectionPool

from django_rq.connection_utils import (
    ConnectionIdentity,
    ConnectionType,
    SentinelAddress,
    TCPAddress,
    get_connection,
    get_connection_by_index,
    get_connection_groups,
    get_connection_identity,
    get_redis_connection,
    get_unique_connection_configs,
)
from django_rq.queues import get_queue, get_queues
from tests.base import DjangoRQTestCase
from tests.fixtures import access_self
from tests.redis_config import REDIS_CONFIG_1, REDIS_CONFIG_2, REDIS_CONFIG_3

QUEUES = settings.RQ_QUEUES


@override_settings(RQ={'AUTOCOMMIT': True})
class ConnectionTest(DjangoRQTestCase):
    def test_get_connection_default(self):
        """
        Test that get_connection returns the right connection based for
        `default` queue.
        """
        config = QUEUES['default']
        connection = get_connection()
        self.assert_connection_kwargs(connection, config)

    def test_get_connection_test(self):
        """
        Test that get_connection returns the right connection based for
        `test` queue.
        """
        config = QUEUES['test']
        connection = get_connection('test')
        self.assert_connection_kwargs(connection, config)

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
            'HOST': REDIS_CONFIG_1.host,
            'PORT': REDIS_CONFIG_1.port,
            'DB': REDIS_CONFIG_1.db,
        }
        connection_params_2 = {
            'HOST': REDIS_CONFIG_2.host,
            'PORT': REDIS_CONFIG_2.port,
            'DB': REDIS_CONFIG_2.db,
        }
        config = {'default': connection_params_1, 'test': connection_params_2}
        with self.assertWarnsMessage(DeprecationWarning, 'Use get_connection_groups() for cron connection indexes.'):
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
            'HOST': REDIS_CONFIG_1.host,
            'PORT': REDIS_CONFIG_1.port,
            'DB': REDIS_CONFIG_1.db,
        }
        connection_params_2 = {
            'HOST': REDIS_CONFIG_2.host,
            'PORT': REDIS_CONFIG_2.port,
            'DB': REDIS_CONFIG_2.db,
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
            'HOST': REDIS_CONFIG_1.host,
            'PORT': REDIS_CONFIG_1.port,
            'DB': REDIS_CONFIG_1.db,
        }
        connection_params_2 = {
            'HOST': REDIS_CONFIG_2.host,
            'PORT': REDIS_CONFIG_2.port,
            'DB': REDIS_CONFIG_2.db,
        }
        connection_params_3 = {
            'HOST': REDIS_CONFIG_3.host,
            'PORT': REDIS_CONFIG_3.port,
            'DB': REDIS_CONFIG_3.db,
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


class ConnectionIdentityTest(SimpleTestCase):
    @override_settings(
        RQ_QUEUES={
            'z-other-db': {'URL': 'redis://localhost/1'},
            'b-explicit': {'HOST': 'localhost', 'PORT': 6379, 'DB': 0},
            'a-url': {'URL': 'redis://user:secret@localhost?port=6379'},
        }
    )
    def test_grouping_and_index_use_effective_tcp_address(self):
        groups = get_connection_groups()
        self.assertEqual(
            [(identity, group.names) for identity, group in groups.items()],
            [
                (ConnectionIdentity(ConnectionType.TCP, TCPAddress('localhost', 6379), 0), ['a-url', 'b-explicit']),
                (ConnectionIdentity(ConnectionType.TCP, TCPAddress('localhost', 6379), 1), ['z-other-db']),
            ],
        )
        self.assertEqual(
            get_connection_identity(get_connection_by_index(1)),
            ConnectionIdentity(ConnectionType.TCP, TCPAddress('localhost', 6379), 1),
        )
        self.assertEqual([q.name for q in get_queues('a-url', 'b-explicit')], ['a-url', 'b-explicit'])
        with self.assertRaises(ValueError):
            get_queues('a-url', 'z-other-db')

    def test_tcp_defaults_and_tls(self):
        identity = ConnectionIdentity(ConnectionType.TCP, TCPAddress('localhost', 6379), 0)
        self.assertEqual(get_connection_identity(Redis.from_url('redis:///0')), identity)
        self.assertEqual(get_connection_identity(Redis.from_url('rediss://localhost')), identity)
        self.assertEqual(get_connection_identity(get_redis_connection({'HOST': None, 'PORT': 6379})), identity)

    def test_unix_socket_path_and_database(self):
        socket = get_redis_connection({'UNIX_SOCKET_PATH': '/tmp/redis.sock', 'DB': 2})
        identity = get_connection_identity(socket)
        self.assertEqual(identity, ConnectionIdentity(ConnectionType.UNIX, '/tmp/redis.sock', 2))
        self.assertEqual(get_connection_identity(Redis.from_url('unix:///tmp/redis.sock?db=2')), identity)
        self.assertNotEqual(get_connection_identity(Redis.from_url('unix:///tmp/other.sock?db=2')), identity)
        self.assertNotEqual(get_connection_identity(Redis.from_url('unix:///tmp/redis.sock?db=3')), identity)

    def test_sentinel_endpoints_and_master(self):
        endpoints = [TCPAddress('one', 26379), TCPAddress('two', 26379)]
        config = {'SENTINELS': endpoints, 'MASTER_NAME': 'main'}
        connection = get_redis_connection(config)
        identity = get_connection_identity(connection)
        self.assertEqual(
            identity, ConnectionIdentity(ConnectionType.SENTINEL, SentinelAddress(tuple(endpoints), 'main'), 0)
        )

        connection.connection_pool.sentinel_manager.sentinels.reverse()
        self.assertEqual(get_connection_identity(connection), identity)
        repeated = get_redis_connection({**config, 'SENTINELS': [*reversed(endpoints), endpoints[0]]})
        self.assertEqual(get_connection_identity(repeated), identity)
        other_master = get_redis_connection({**config, 'MASTER_NAME': 'other'})
        self.assertNotEqual(get_connection_identity(other_master), identity)

    @override_settings(
        RQ_QUEUES={
            'a-cache': {'USE_REDIS_CACHE': 'first'},
            'b-cache': {'USE_REDIS_CACHE': 'shared'},
            'c-cache': {'USE_REDIS_CACHE': 'separate'},
        }
    )
    def test_opaque_targets_group_only_by_shared_pool(self):
        class CustomConnection(Connection):
            pass

        pool = ConnectionPool(connection_class=CustomConnection)
        clients = [
            Redis(connection_pool=pool),
            Redis(connection_pool=pool),
            Redis(connection_pool=ConnectionPool(connection_class=CustomConnection)),
        ]
        with patch('django_rq.connection_utils.get_redis_connection', side_effect=clients):
            groups = get_connection_groups()
        self.assertEqual([group.names for group in groups.values()], [['a-cache', 'b-cache'], ['c-cache']])

    @override_settings(RQ_QUEUES={'a-invalid': {}, 'b-valid': {'URL': 'redis://localhost'}})
    def test_failed_connections_keep_their_index(self):
        with self.assertRaises(KeyError):
            get_connection_by_index(0)
        self.assertEqual(
            get_connection_identity(get_connection_by_index(1)),
            ConnectionIdentity(ConnectionType.TCP, TCPAddress('localhost', 6379), 0),
        )


class RedisCacheTest(DjangoRQTestCase):
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
        self.assertEqual(queue.name, queueName)

        cacheHost = settings.CACHES[queueName]['LOCATION'].split(':')[0]
        cachePort = settings.CACHES[queueName]['LOCATION'].split(':')[1]
        cacheDBNum = settings.CACHES[queueName]['OPTIONS']['DB']

        self.assert_connection_kwargs(
            queue.connection, {'host': cacheHost, 'port': int(cachePort), 'db': int(cacheDBNum), 'password': None}
        )
