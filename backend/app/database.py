"""
Async SQLAlchemy 2.0 database layer.

Connection pooling is configured for high-concurrency workloads.
All sessions are async — never use synchronous session methods.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import sys
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# NullPool is used in testing environments to avoid connection leaks.
# Production uses the default QueuePool configured via pool_size / max_overflow.

_engine_kwargs: dict[str, Any] = {
    "echo": settings.app_debug,
    "pool_pre_ping": True,          # Detect stale connections before use
    "pool_recycle": settings.database_pool_recycle,
}

if settings.app_env != "testing":
    _engine_kwargs.update(
        {
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
            "pool_timeout": settings.database_pool_timeout,
        }
    )
else:
    _engine_kwargs["poolclass"] = NullPool
_engine_url = settings.database_url
# Pytest uses an isolated in-memory DB for health checks; scripts running in
# the CI testing environment still need to target the migrated DATABASE_URL.
if settings.app_env == "testing" and any("pytest" in arg for arg in sys.argv):
    _engine_url = "sqlite+aiosqlite:///:memory:"

engine: AsyncEngine = create_async_engine(_engine_url, **_engine_kwargs)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # Prevents lazy-load failures after commit
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency — provides a transactional session per request
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a SQLAlchemy async session scoped to the current HTTP request.

    The session is committed on success and rolled back on any exception,
    then always closed to return the connection to the pool.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Context manager for use outside of FastAPI (background jobs, seeds, etc.)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Health check helper
# ---------------------------------------------------------------------------
async def check_database_health() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("database_health_check_failed", error=str(exc))
        return False
