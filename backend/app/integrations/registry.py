"""
Provider registry — resolves an IntegrationAccount into a live TaskProvider.

Usage
─────
    provider = await ProviderRegistry.build(account, session)
    boards   = await provider.get_boards()
    await provider.close()

Or as an async context manager (preferred):

    async with ProviderRegistry.open(account) as provider:
        boards = await provider.get_boards()
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.integrations.base import ProviderType, TaskProvider
from app.integrations.encryption import safe_decrypt

if TYPE_CHECKING:
    from app.models.integration_account import IntegrationAccount


class ProviderRegistry:

    @staticmethod
    def build(account: "IntegrationAccount") -> TaskProvider:
        """
        Instantiate the correct provider adapter for `account`.
        Tokens are decrypted inline; the caller owns the lifecycle.
        """
        pt = ProviderType(account.provider)

        if pt == ProviderType.JIRA:
            from app.integrations.providers.jira.adapter import JiraAdapter
            return JiraAdapter(
                access_token=safe_decrypt(account.encrypted_access_token) or "",
                refresh_token=safe_decrypt(account.encrypted_refresh_token),
                cloud_id=account.extra_data.get("cloud_id", ""),
                account_id=account.db_account_id,
            )

        if pt == ProviderType.MICROSOFT:
            from app.integrations.providers.microsoft.adapter import MicrosoftAdapter
            return MicrosoftAdapter(
                access_token=safe_decrypt(account.encrypted_access_token) or "",
                refresh_token=safe_decrypt(account.encrypted_refresh_token),
                tenant_id=account.extra_data.get("tenant_id", "common"),
                account_id=account.db_account_id,
            )

        if pt == ProviderType.TRELLO:
            from app.integrations.providers.trello.adapter import TrelloAdapter
            return TrelloAdapter(
                api_key=safe_decrypt(account.encrypted_access_token) or "",
                api_token=safe_decrypt(account.encrypted_refresh_token) or "",
                account_id=account.db_account_id,
            )

        if pt == ProviderType.GITHUB:
            from app.integrations.providers.github.adapter import GitHubAdapter
            return GitHubAdapter(
                access_token=safe_decrypt(account.encrypted_access_token) or "",
                account_id=account.db_account_id,
            )

        raise ValueError(f"Unsupported provider: {account.provider}")

    @staticmethod
    @asynccontextmanager
    async def open(account: "IntegrationAccount") -> AsyncIterator[TaskProvider]:
        """Context manager that builds and closes a provider adapter."""
        provider = ProviderRegistry.build(account)
        try:
            yield provider
        finally:
            await provider.close()
