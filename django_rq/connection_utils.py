from typing import Any

import redis
from redis import Redis
from redis.sentinel import Sentinel


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


def filter_connection_params(queue_params):
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
    )

    # return {p:v for p,v in queue_params.items() if p in CONNECTION_PARAMS}
    # Dict comprehension compatible with python 2.6
    return dict((p, v) for (p, v) in queue_params.items() if p in CONNECTION_PARAMS)


def get_unique_connection_configs(config: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """
    Returns a list of unique Redis connections from config in deterministic order.
    Configs are ordered based on sorted queue names, allowing reliable use of
    connection_index to access specific connections.
    """
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
