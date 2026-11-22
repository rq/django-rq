import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple

import redis
from redis import Redis
from redis.connection import Connection, SSLConnection, UnixDomainSocketConnection
from redis.sentinel import Sentinel, SentinelConnectionPool


class ConnectionType(Enum):
    TCP = 'tcp'
    UNIX = 'unix'
    SENTINEL = 'sentinel'
    UNKNOWN = 'unknown'
    FAILED_QUEUE = 'failed_queue'


class TCPAddress(NamedTuple):
    host: str
    port: int


class SentinelAddress(NamedTuple):
    endpoints: tuple[TCPAddress, ...]
    service_name: str


ConnectionAddress = TCPAddress | SentinelAddress | str | int


@dataclass(frozen=True)
class ConnectionIdentity:
    connection_type: ConnectionType
    address: ConnectionAddress
    db: int | None


<<<<<<< HEAD
@dataclass
class ConnectionGroup:
    identity: ConnectionIdentity
    names: list[str]
    _connection: Redis | Exception

    @property
    def connection(self) -> Redis:
        """Return the Redis client or raise its original initialization error."""
        if isinstance(self._connection, Exception):
            raise self._connection
        return self._connection
=======
class ConnectionGroup(NamedTuple):
    names: list[str]
    connection: Redis | Exception

    def client(self) -> Redis:
        if isinstance(self.connection, Exception):
            raise self.connection
        return self.connection
>>>>>>> master


def get_redis_connection(config: dict[str, Any], use_strict_redis: bool = False) -> Redis:
    """
    Returns a redis connection from a connection config
    """
    redis_cls = redis.StrictRedis if use_strict_redis else redis.Redis

    if 'URL' in config:
        if config.get('SSL') or config['URL'].startswith('rediss://'):
            return redis_cls.from_url(
                config['URL'],
                db=config.get('DB'),
                ssl_cert_reqs=config.get('SSL_CERT_REQS', 'required'),
            )
        else:
            return redis_cls.from_url(
                config['URL'],
                db=config.get('DB'),
            )

    if 'USE_REDIS_CACHE' in config.keys():
        try:
            # Assume that we're using django-redis
            from django_redis import get_redis_connection as get_redis

            return get_redis(config['USE_REDIS_CACHE'])
        except ImportError:
            pass

        from django.core.cache import caches

        cache = caches[config['USE_REDIS_CACHE']]
        # We're using django-redis-cache
        try:
            return cache._client  # type: ignore[attr-defined]
        except AttributeError:
            # For django-redis-cache > 0.13.1
            return cache.get_master_client()  # type: ignore[attr-defined]

    if 'UNIX_SOCKET_PATH' in config:
        return redis_cls(unix_socket_path=config['UNIX_SOCKET_PATH'], db=config['DB'])

    if 'SENTINELS' in config:
        connection_kwargs: dict[str, Any] = {
            'db': config.get('DB'),
            'password': config.get('PASSWORD'),
            'username': config.get('USERNAME'),
            'socket_timeout': config.get('SOCKET_TIMEOUT'),
        }
        connection_kwargs.update(config.get('CONNECTION_KWARGS', {}))
        sentinel_kwargs = config.get('SENTINEL_KWARGS', {})
        sentinel = Sentinel(config['SENTINELS'], sentinel_kwargs=sentinel_kwargs, **connection_kwargs)
        return sentinel.master_for(
            service_name=config['MASTER_NAME'],
            redis_class=redis_cls,
        )

    return redis_cls(
        host=config['HOST'],
        port=config['PORT'],
        db=config.get('DB', 0),
        username=config.get('USERNAME', None),
        password=config.get('PASSWORD'),
        ssl=config.get('SSL', False),
        ssl_cert_reqs=config.get('SSL_CERT_REQS', 'required'),
        **config.get('REDIS_CLIENT_KWARGS', {}),
    )


def get_connection(
    name: str = 'default',
    use_strict_redis: bool = False,
) -> Redis:
    """
    Returns a Redis connection to use based on parameters in settings.RQ_QUEUES
    """
    from .settings import QUEUES

    return get_redis_connection(QUEUES[name], use_strict_redis)


def get_connection_identity(connection: Redis) -> ConnectionIdentity:
    """Identify a configured Redis database or fall back to the client pool's identity."""
    pool = connection.connection_pool
    kwargs = pool.connection_kwargs
    connection_class = getattr(pool, 'connection_class', None)
    fallback = ConnectionIdentity(ConnectionType.UNKNOWN, id(pool), None)
    try:
        db = int(kwargs.get('db') or 0)
        if isinstance(pool, SentinelConnectionPool):
            endpoints = set()
            for sentinel in pool.sentinel_manager.sentinels:
                options = sentinel.connection_pool.connection_kwargs
                endpoints.add(TCPAddress(options['host'], int(options['port'])))
            if endpoints:
                address = SentinelAddress(tuple(sorted(endpoints)), pool.service_name)
                return ConnectionIdentity(ConnectionType.SENTINEL, address, db)
        elif connection_class is UnixDomainSocketConnection and kwargs.get('path'):
            return ConnectionIdentity(ConnectionType.UNIX, kwargs['path'], db)
        elif connection_class in (Connection, SSLConnection):
            host = kwargs.get('host')
            if host is None:
                host = 'localhost'
            port = int(kwargs.get('port', 6379))
            return ConnectionIdentity(ConnectionType.TCP, TCPAddress(host, port), db)
    except (KeyError, TypeError, ValueError):
        # Incomplete metadata can identify the wrong target, especially for Sentinel.
        return fallback
    return fallback


<<<<<<< HEAD
def get_connection_groups() -> list[ConnectionGroup]:
    """Group queue names by Redis database, ordered by each group's first queue name."""
    from .settings import get_queues_list

    group_by_identity: dict[ConnectionIdentity, ConnectionGroup] = {}
=======
def get_connection_groups() -> dict[ConnectionIdentity, ConnectionGroup]:
    """Group queue names in sorted order and retain a client for each database."""
    from .settings import get_queues_list

    groups: dict[ConnectionIdentity, ConnectionGroup] = {}
>>>>>>> master
    for config in get_queues_list():
        name = config['name']
        try:
            connection = get_redis_connection(config['connection_config'])
        except Exception as error:
            # Keep the index reserved when a client cannot be constructed.
<<<<<<< HEAD
            identity = ConnectionIdentity(ConnectionType.FAILED_QUEUE, name, None)
            group_by_identity[identity] = ConnectionGroup(identity, [name], error)
            continue
        identity = get_connection_identity(connection)
        group = group_by_identity.setdefault(identity, ConnectionGroup(identity, [], connection))
        group.names.append(name)
    return list(group_by_identity.values())
=======
            groups[ConnectionIdentity(ConnectionType.FAILED_QUEUE, name, None)] = ConnectionGroup([name], error)
            continue
        group = groups.setdefault(get_connection_identity(connection), ConnectionGroup([], connection))
        group.names.append(name)
    return groups
>>>>>>> master


def get_connection_label(identity: ConnectionIdentity) -> str:
    address = identity.address
    if isinstance(address, TCPAddress):
        return f'{address.host}:{address.port}/{identity.db}'
    if isinstance(address, SentinelAddress):
        hosts = ', '.join(f'{host}:{port}' for host, port in address.endpoints)
        return f'{address.service_name}/{identity.db} ({hosts})'
    if identity.connection_type is ConnectionType.UNIX:
        return f'{address}/{identity.db}'
    return '—'


def filter_connection_params(queue_params: dict[str, Any]) -> dict[str, Any]:
    """
    Filters the queue params to keep only the connection related params.
    """
    CONNECTION_PARAMS = (
        'URL',
        'DB',
        'USE_REDIS_CACHE',
        'UNIX_SOCKET_PATH',
        'HOST',
        'PORT',
        'PASSWORD',
        'SENTINELS',
        'MASTER_NAME',
        'SOCKET_TIMEOUT',
        'SSL',
        'CONNECTION_KWARGS',
        'SSL_CERT_REQS',
    )

    # return {p:v for p,v in queue_params.items() if p in CONNECTION_PARAMS}
    # Dict comprehension compatible with python 2.6
    return dict((p, v) for (p, v) in queue_params.items() if p in CONNECTION_PARAMS)


def get_unique_connection_configs(config: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return distinct connection configurations, ordered by queue name.

    Deprecated. Cron indexes follow the order returned by get_connection_groups().
    """
    warnings.warn(
        'get_unique_connection_configs() is deprecated. Use get_connection_groups() for cron connection indexes.',
        DeprecationWarning,
        stacklevel=2,
    )
    if config is None:
        from .settings import QUEUES

        config = QUEUES

    connection_configs = []
    # Sort queue names to ensure deterministic ordering
    for key in sorted(config.keys()):
        value = filter_connection_params(config[key])
        if value not in connection_configs:
            connection_configs.append(value)
    return connection_configs


def get_connection_by_index(index: int) -> Redis:
    """Return a client for the database at the specified group index."""
<<<<<<< HEAD
    return get_connection_groups()[index].connection
=======
    return list(get_connection_groups().values())[index].client()
>>>>>>> master
