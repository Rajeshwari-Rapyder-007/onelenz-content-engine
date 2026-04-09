import json
import os
from typing import Any, Optional

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

_redis_client: redis.Redis | None = None

# Backwards-compatible alias for auth service which imports redis_client directly.
# In FastAPI (single long-lived loop) a module-level singleton is fine.
redis_client: redis.Redis = redis.from_url(REDIS_URL, decode_responses=True)


def _get_client() -> redis.Redis:
    """Return a Redis client, creating a new one if needed.

    Creates a fresh client when the previous one's connection pool
    is tied to a closed event loop (happens in Celery prefork workers).
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def reset_client() -> None:
    """Close and discard the current Redis client.

    Call this at the end of each Celery task so the next task
    gets a fresh client bound to its own event loop.
    """
    global _redis_client
    _redis_client = None


def _key(service: str, key_name: str) -> str:
    """Build a Redis key with environment prefix.

    Pattern: {env}:onelenz:{service}:{key_name}
    """
    return f"{ENVIRONMENT}:onelenz:{service}:{key_name}"


async def get_redis() -> redis.Redis:
    """FastAPI dependency that returns the Redis client."""
    return _get_client()


async def hset_json(
    service: str, key_name: str, field: str, value: dict[str, Any]
) -> None:
    """HSET a JSON-serialized value."""
    full_key = _key(service, key_name)
    await _get_client().hset(full_key, field, json.dumps(value, default=str))


async def hget_json(
    service: str, key_name: str, field: str
) -> Optional[dict[str, Any]]:
    """HGET and deserialize JSON. Returns None if not found."""
    full_key = _key(service, key_name)
    raw = await _get_client().hget(full_key, field)
    if raw is None:
        return None
    return json.loads(raw)


async def hdel(service: str, key_name: str, field: str) -> None:
    """HDEL a hash field."""
    full_key = _key(service, key_name)
    await _get_client().hdel(full_key, field)
