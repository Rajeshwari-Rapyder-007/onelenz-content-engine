import os

from shared.logging import get_logger
from shared.redis.client import _get_client

logger = get_logger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
LOCK_TTL_SECONDS = 2100  # 35 minutes (longer than 30 min task timeout)


def _lock_key(config_id: int) -> str:
    return f"{ENVIRONMENT}:onelenz:email:sync_lock:{config_id}"


async def acquire_lock(config_id: int) -> bool:
    """Try to acquire sync lock. Returns True if acquired, False if already locked."""
    key = _lock_key(config_id)
    acquired = await _get_client().set(key, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("Sync lock exists, skipping", extra={"x_config_id": config_id})
    return bool(acquired)


async def extend_lock(config_id: int) -> None:
    """Extend lock TTL — heartbeat during long syncs."""
    key = _lock_key(config_id)
    await _get_client().expire(key, LOCK_TTL_SECONDS)


async def release_lock(config_id: int) -> None:
    """Release sync lock."""
    key = _lock_key(config_id)
    await _get_client().delete(key)
