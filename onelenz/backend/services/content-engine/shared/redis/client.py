import json
import os
from typing import Any, Optional

import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

redis_client: redis.Redis = redis.from_url(REDIS_URL, decode_responses=True)


def _key(service: str, key_name: str) -> str:
    """Build a Redis key with environment prefix.

    Pattern: {env}:onelenz:{service}:{key_name}
    """
    return f"{ENVIRONMENT}:onelenz:{service}:{key_name}"


async def get_redis() -> redis.Redis:
    """FastAPI dependency that returns the Redis client."""
    return redis_client


async def hset_json(
    service: str, key_name: str, field: str, value: dict[str, Any]
) -> None:
    """HSET a JSON-serialized value."""
    full_key = _key(service, key_name)
    await redis_client.hset(full_key, field, json.dumps(value, default=str))


async def hget_json(
    service: str, key_name: str, field: str
) -> Optional[dict[str, Any]]:
    """HGET and deserialize JSON. Returns None if not found."""
    full_key = _key(service, key_name)
    raw = await redis_client.hget(full_key, field)
    if raw is None:
        return None
    return json.loads(raw)


async def hdel(service: str, key_name: str, field: str) -> None:
    """HDEL a hash field."""
    full_key = _key(service, key_name)
    await redis_client.hdel(full_key, field)
