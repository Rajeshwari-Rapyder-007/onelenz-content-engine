import asyncio

from shared.db.adapter import get_worker_session_factory, reset_engine
from shared.logging import get_logger
from shared.redis.client import reset_client as reset_redis

from .celery_app import celery
from .sync_lock import acquire_lock, release_lock

logger = get_logger(__name__)


def _run_async(coro):
    """Run an async function from a sync Celery task.

    Resets Redis + DB connections, then creates a fresh event loop to avoid
    'Event loop is closed' / 'attached to a different loop' errors when
    prefork workers reuse the same process for multiple tasks.
    """
    reset_redis()
    reset_engine()
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(name="app.workers.sync_tasks.incremental_sync_all")
def incremental_sync_all():
    """Scheduled task: run incremental sync for all active integrations."""
    _run_async(_incremental_sync_all())


@celery.task(
    name="app.workers.sync_tasks.sync_single",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def sync_single(self, config_id: int):
    """Sync a single integration with lock."""
    try:
        _run_async(_sync_single(config_id))
    except Exception as exc:
        logger.error(
            "Sync task failed, retrying",
            extra={"x_config_id": config_id, "x_retry": self.request.retries},
            exc_info=True,
        )
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@celery.task(name="app.workers.sync_tasks.initial_full_fetch")
def initial_full_fetch(config_id: int):
    """One-time task: run initial full fetch after OAuth callback."""
    _run_async(_initial_full_fetch(config_id))


async def _incremental_sync_all():
    """Query active integrations and dispatch sync for each."""
    from ..repositories.integration_repository import IntegrationRepository

    async with get_worker_session_factory()() as session:
        repo = IntegrationRepository(session)
        active_integrations = await repo.find_all_connected("EMAIL")

        logger.info(
            "Starting incremental sync for all",
            extra={"x_count": len(active_integrations)},
        )

        for integration in active_integrations:
            sync_single.delay(integration.inc_config_id)


async def _sync_single(config_id: int):
    """Run incremental sync with lock protection."""
    from ..services.sync_service import incremental_sync

    locked = await acquire_lock(config_id)
    if not locked:
        return

    try:
        async with get_worker_session_factory()() as session:
            try:
                await incremental_sync(config_id, session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await release_lock(config_id)


async def _initial_full_fetch(config_id: int):
    """Run full fetch with lock protection."""
    from ..services.sync_service import full_fetch

    locked = await acquire_lock(config_id)
    if not locked:
        logger.warning("Lock exists for full fetch", extra={"x_config_id": config_id})
        return

    try:
        async with get_worker_session_factory()() as session:
            try:
                await full_fetch(config_id, session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await release_lock(config_id)
