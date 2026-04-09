import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/onelenz",
)

_ENGINE_KWARGS = {
    "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
    "echo": os.getenv("DB_ECHO", "false").lower() == "true",
}

# Module-level singletons — work fine in FastAPI (single long-lived loop).
engine = create_async_engine(DATABASE_URL, **_ENGINE_KWARGS)
async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)

# ---------------------------------------------------------------------------
#  Lazy engine for Celery workers (fresh engine per event loop)
# ---------------------------------------------------------------------------
_worker_engine = None
_worker_session_factory = None


def get_worker_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to a fresh engine.

    Call reset_engine() before each Celery task to discard stale connections.
    """
    global _worker_engine, _worker_session_factory
    if _worker_engine is None:
        _worker_engine = create_async_engine(DATABASE_URL, **_ENGINE_KWARGS)
        _worker_session_factory = async_sessionmaker(
            _worker_engine, class_=AsyncSession, expire_on_commit=False,
        )
    return _worker_session_factory


def reset_engine() -> None:
    """Discard engine so the next task gets a fresh connection pool."""
    global _worker_engine, _worker_session_factory
    _worker_engine = None
    _worker_session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
