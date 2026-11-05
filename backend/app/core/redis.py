"""Redis client wrapper.

Used for caching (short-lived computed values), distributed locks, and
session/rate-limit storage. Connections are created lazily so the app can
start without Redis up (health endpoint degrades gracefully).
"""

from __future__ import annotations

import functools
import logging

import redis
from redis.connection import ConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)


@functools.lru_cache
def get_redis() -> redis.Redis:
    """Return a shared Redis client (pooled)."""
    pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    client = redis.Redis(connection_pool=pool)
    try:
        client.ping()
        logger.info("Redis connection established")
    except Exception as exc:  # pragma: no cover - degraded startup path
        logger.warning("Redis unavailable at startup: %s", exc)
    return client


def get_cache() -> redis.Redis:
    """Alias for get_redis — names the role (cache)."""
    return get_redis()


class Cache:
    """Tiny typed wrapper over Redis for common cache operations."""

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._client = client or get_redis()

    def get(self, key: str) -> str | None:
        try:
            return self._client.get(key)
        except redis.RedisError as exc:
            logger.warning("Cache get failed: %s", exc)
            return None

    def set(self, key: str, value: str, ttl: int = 300) -> None:
        try:
            self._client.set(key, value, ex=ttl)
        except redis.RedisError as exc:
            logger.warning("Cache set failed: %s", exc)

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except redis.RedisError as exc:
            logger.warning("Cache delete failed: %s", exc)

    def acquire_lock(self, key: str, ttl: int = 30) -> bool:
        """Best-effort non-blocking lock. Returns True if acquired."""
        try:
            return bool(self._client.set(f"lock:{key}", "1", nx=True, ex=ttl))
        except redis.RedisError as exc:
            logger.warning("Lock acquire failed: %s", exc)
            return False

    def release_lock(self, key: str) -> None:
        try:
            self._client.delete(f"lock:{key}")
        except redis.RedisError as exc:
            logger.warning("Lock release failed: %s", exc)
