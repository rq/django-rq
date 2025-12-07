from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError


@dataclass(frozen=True)
class RedisConfig:
    host: str
    port: int
    db: int


def _find_empty_databases(host: str, port: int, *, required: int) -> Sequence[int]:
    """
    Find a set of empty Redis databases that can be used for tests.

    Raises RuntimeError if we cannot connect or if we cannot find the requested
    number of empty databases. Sentinel ports are intentionally not probed.
    """
    # try:
    #     redis = Redis(host=host, port=port, db=0)
    # except Exception as exc:  # pragma: no cover - defensive guard
    #     raise RuntimeError(f"Refusing to run tests: cannot connect to Redis at {host}:{port}") from exc

    empty_databases: list[int] = []

    for db in range(16):
        try:
            if Redis(host=host, port=port, db=db).dbsize() == 0:
                empty_databases.append(db)
                if len(empty_databases) == required:
                    break
        except RedisError as exc:  # pragma: no cover - defensive guard
            raise RuntimeError(
                f"Refusing to run tests: unable to inspect Redis database {db} on {host}:{port}"
            ) from exc

    if len(empty_databases) < required:
        raise RuntimeError(
            f"Refusing to run tests: need {required} empty Redis databases on {host}:{port}, "
            f"but only found {len(empty_databases)}."
        )

    return empty_databases


REDIS_HOST = 'localhost'
REDIS_PORT = 6379
databases = _find_empty_databases(REDIS_HOST, REDIS_PORT, required=3)

REDIS_CONFIG_1 = RedisConfig(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=databases[0],
)
REDIS_CONFIG_2 = RedisConfig(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=databases[1],
)
REDIS_CONFIG_3 = RedisConfig(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=databases[2],
)
