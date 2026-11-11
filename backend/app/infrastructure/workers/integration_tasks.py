"""
Celery tasks for multi-provider integration syncs.

Schedules (added to celery_app.py beat_schedule):
  integration-sync-5min   — every 5 min, incremental sync all active accounts
  integration-sync-1hour  — every hour, full sync all active accounts

Each task runs per-provider adapters via ProviderRegistry, so adding a
new provider only requires implementing TaskProvider — no changes here.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.logging_config import get_logger
from app.infrastructure.workers.celery_app import celery_app

logger = get_logger(__name__)


async def _run_and_dispose(coro: Any) -> Any:
    try:
        return await coro
    finally:
        from app.database import engine

        await engine.dispose()


def _run(coro: Any) -> Any:
    """Execute an async coroutine inside a synchronous Celery task."""
    return asyncio.run(_run_and_dispose(coro))


# ── Incremental sync — every 5 minutes ───────────────────────────────────────

@celery_app.task(
    name="integration_incremental_sync_all",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="default",
)
def integration_incremental_sync_all(self: Any) -> dict[str, Any]:
    """Incremental sync: pull updates since last_sync_at for all active accounts."""
    return _run(_async_incremental_sync_all())


async def _async_incremental_sync_all() -> dict[str, Any]:
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.integrations.base import ProviderType
    from app.integrations.registry import ProviderRegistry
    from app.models.integration_account import IntegrationAccount

    results: list[dict] = []

    async with AsyncSessionLocal() as session:
        stmt = (
            select(IntegrationAccount)
            .where(IntegrationAccount.is_active.is_(True))
        )
        accounts = (await session.execute(stmt)).scalars().all()

        for account in accounts:
            try:
                async with ProviderRegistry.open(account) as provider:
                    boards = await provider.get_boards()
                    total  = 0
                    for board in boards:
                        count = await provider.sync_board(board.id)
                        total += count

                account.last_sync_at = datetime.now(timezone.utc)
                session.add(account)
                results.append({"account_id": account.id, "provider": account.provider, "synced": total})

            except Exception as exc:
                logger.error(
                    "integration.incremental_sync_failed",
                    account_id=account.id,
                    provider=account.provider,
                    error=str(exc),
                )
                results.append({"account_id": account.id, "provider": account.provider, "error": str(exc)})

        await session.commit()

    logger.info("integration.incremental_sync_complete", results=results)
    return {"synced_accounts": len(results), "results": results}


# ── Full sync — every hour ────────────────────────────────────────────────────

@celery_app.task(
    name="integration_full_sync_all",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    queue="default",
)
def integration_full_sync_all(self: Any) -> dict[str, Any]:
    """Full sync: re-pull everything for all active accounts."""
    return _run(_async_full_sync_all())


async def _async_full_sync_all() -> dict[str, Any]:
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.integrations.registry import ProviderRegistry
    from app.models.integration_account import IntegrationAccount

    results: list[dict] = []

    async with AsyncSessionLocal() as session:
        stmt = select(IntegrationAccount).where(IntegrationAccount.is_active.is_(True))
        accounts = (await session.execute(stmt)).scalars().all()

        for account in accounts:
            try:
                async with ProviderRegistry.open(account) as provider:
                    boards = await provider.get_boards()
                    total  = 0
                    for board in boards:
                        count = await provider.sync_board(board.id)
                        total += count

                account.last_sync_at = datetime.now(timezone.utc)
                session.add(account)
                results.append({"account_id": account.id, "synced": total})

            except Exception as exc:
                logger.error(
                    "integration.full_sync_failed",
                    account_id=account.id,
                    error=str(exc),
                )
                results.append({"account_id": account.id, "error": str(exc)})

        await session.commit()

    logger.info("integration.full_sync_complete", results=results)
    return {"results": results}


# ── Token refresh — every 45 minutes ─────────────────────────────────────────

@celery_app.task(
    name="integration_refresh_expiring_tokens",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="high_priority",
)
def integration_refresh_expiring_tokens(self: Any) -> dict[str, Any]:
    """
    Proactively refresh access tokens that expire within the next 10 minutes.
    Prevents mid-sync token expiry failures.
    """
    return _run(_async_refresh_expiring_tokens())


async def _async_refresh_expiring_tokens() -> dict[str, Any]:
    from sqlalchemy import and_, select
    from app.database import AsyncSessionLocal
    from app.integrations.encryption import decrypt_token, encrypt_token
    from app.models.integration_account import IntegrationAccount

    soon       = datetime.now(timezone.utc) + timedelta(minutes=10)
    refreshed  = []

    async with AsyncSessionLocal() as session:
        stmt = select(IntegrationAccount).where(
            and_(
                IntegrationAccount.is_active.is_(True),
                IntegrationAccount.token_expires_at <= soon,
                IntegrationAccount.encrypted_refresh_token.isnot(None),
            )
        )
        accounts = (await session.execute(stmt)).scalars().all()

        for account in accounts:
            try:
                refresh_token = decrypt_token(account.encrypted_refresh_token)
                new_tokens = await _do_refresh(account.provider, refresh_token)
                if new_tokens:
                    account.encrypted_access_token = encrypt_token(new_tokens.access_token)
                    if new_tokens.refresh_token:
                        account.encrypted_refresh_token = encrypt_token(new_tokens.refresh_token)
                    account.token_expires_at = new_tokens.expires_at
                    session.add(account)
                    refreshed.append(account.id)
                    logger.info(
                        "integration.token_refreshed",
                        account_id=account.id,
                        provider=account.provider,
                    )
            except Exception as exc:
                logger.error(
                    "integration.token_refresh_failed",
                    account_id=account.id,
                    error=str(exc),
                )

        await session.commit()

    return {"refreshed": refreshed}


async def _do_refresh(provider: str, refresh_token: str) -> Any:
    """Dispatch to the correct OAuth client for token refresh."""
    if provider == "jira":
        from app.integrations.oauth.jira import get_jira_oauth
        return await get_jira_oauth().refresh_access_token(refresh_token)
    if provider == "microsoft":
        from app.integrations.oauth.microsoft import get_microsoft_oauth
        return await get_microsoft_oauth().refresh_access_token(refresh_token)
    return None  # Trello tokens don't expire


# ── Register beat schedule entries ────────────────────────────────────────────
# Add these to celery_app.py's beat_schedule dict:
#
# "integration-incremental-sync-5min": {
#     "task":     "integration_incremental_sync_all",
#     "schedule": 300,
# },
# "integration-full-sync-1hour": {
#     "task":     "integration_full_sync_all",
#     "schedule": 3600,
# },
# "integration-token-refresh-45min": {
#     "task":     "integration_refresh_expiring_tokens",
#     "schedule": 2700,
# },
