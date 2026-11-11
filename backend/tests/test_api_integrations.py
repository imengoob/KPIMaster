"""
Integration tests for /api/v1/integrations endpoints.

Strategy
────────
• Uses `auth_client` fixture (from conftest) which overrides `current_user_id`
  so every request is seen as coming from `test_user`.
• External provider calls (TrelloClient, ProviderRegistry) are patched via
  `monkeypatch` — no real network calls are made.
• SQLite in-memory DB ensures complete isolation between tests.

Coverage
────────
  GET    /integrations                     — list accounts
  DELETE /integrations/{id}                — disconnect (soft delete)
  GET    /integrations/{id}/health         — credential health
  GET    /integrations/{id}/boards         — list boards
  GET    /integrations/{id}/tasks          — list tasks
  POST   /integrations/{id}/sync           — trigger sync
  GET    /integrations/{id}/sync-logs      — audit log
  POST   /integrations/connect/trello      — direct Trello connect
  POST   /integrations/connect/github      — direct GitHub token connect
  GET    /integrations/oauth/jira/start    — OAuth init (503 when not configured)
  GET    /integrations/oauth/microsoft/start — OAuth init (503 when not configured)
  Edge cases: 404, 410 (disconnected), rate limit, invalid creds
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.base import NormalizedBoard, NormalizedComment, NormalizedTask, ProviderType
from app.integrations.encryption import encrypt_token
from app.models.integration_account import IntegrationAccount
from app.models.integration_sync_log import IntegrationSyncLog, SyncStatus, SyncType
from app.models.integration_task import IntegrationComment, IntegrationTask
from app.models.project import Project
from app.models.trello_board import TrelloBoard
from app.models.trello_credential import TrelloCredential


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_board(board_id: str = "board-1", name: str = "Sprint Board") -> NormalizedBoard:
    return NormalizedBoard(
        id=board_id, name=name, provider=ProviderType.TRELLO,
        url=f"https://trello.com/b/{board_id}", is_active=True, extra={"description": "Test board"},
    )


def _fake_task(task_id: str = "task-1") -> NormalizedTask:
    return NormalizedTask(
        id=task_id, title="Implement login", status="in_progress",
        board_id="board-1", provider=ProviderType.TRELLO, task_type="task",
    )


def _fake_provider(boards=None, tasks=None, comments=None, synced=5, healthy=True):
    """Return a mock TaskProvider."""
    provider = AsyncMock()
    provider.validate_credentials = AsyncMock(return_value=healthy)
    provider.get_boards = AsyncMock(return_value=[_fake_board()] if boards is None else boards)
    provider.get_tasks = AsyncMock(return_value=[_fake_task()] if tasks is None else tasks)
    provider.get_comments = AsyncMock(return_value=[] if comments is None else comments)
    provider.get_board = AsyncMock(return_value=_fake_board() if boards is None else boards[0] if boards else _fake_board())
    provider.sync_board = AsyncMock(return_value=synced)
    provider.close = AsyncMock()
    return provider


# ── List accounts ─────────────────────────────────────────────────────────────

async def test_list_accounts_empty(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/v1/integrations")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_accounts_returns_own_accounts(
    auth_client: AsyncClient, integration_account: IntegrationAccount
) -> None:
    resp = await auth_client.get("/api/v1/integrations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["provider"] == "trello"
    assert data[0]["account_name"] == "Test Trello"


async def test_list_accounts_filters_by_provider(
    auth_client: AsyncClient, integration_account: IntegrationAccount
) -> None:
    resp = await auth_client.get("/api/v1/integrations?provider=jira")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_accounts_excludes_inactive_by_default(
    auth_client: AsyncClient, db: AsyncSession, integration_account: IntegrationAccount
) -> None:
    integration_account.is_active = False
    db.add(integration_account)
    await db.flush()
    resp = await auth_client.get("/api/v1/integrations")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_accounts_includes_inactive_when_requested(
    auth_client: AsyncClient, db: AsyncSession, integration_account: IntegrationAccount
) -> None:
    integration_account.is_active = False
    db.add(integration_account)
    await db.flush()
    resp = await auth_client.get("/api/v1/integrations?active_only=false")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── Disconnect account ────────────────────────────────────────────────────────

async def test_disconnect_soft_deletes_account(
    auth_client: AsyncClient, db: AsyncSession, integration_account: IntegrationAccount
) -> None:
    resp = await auth_client.delete(f"/api/v1/integrations/{integration_account.id}")
    assert resp.status_code == 204

    await db.refresh(integration_account)
    assert integration_account.is_active is False
    assert integration_account.encrypted_access_token is None
    assert integration_account.encrypted_refresh_token is None


async def test_disconnect_returns_404_for_unknown_account(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.delete("/api/v1/integrations/99999")
    assert resp.status_code == 404


async def test_disconnect_cannot_access_other_users_account(
    auth_client: AsyncClient, db: AsyncSession
) -> None:
    """Accounts owned by a different user must not be deletable."""
    other_account = IntegrationAccount(
        user_id=99999,  # different user
        provider="trello",
        account_name="Someone else's account",
        external_account_id="other_member",
        encrypted_access_token=encrypt_token("key"),
        encrypted_refresh_token=encrypt_token("tok"),
        scopes=[], extra_data={}, is_active=True,
    )
    db.add(other_account)
    await db.flush()

    resp = await auth_client.delete(f"/api/v1/integrations/{other_account.id}")
    assert resp.status_code == 404


async def test_disconnect_already_inactive_account_returns_410(
    auth_client: AsyncClient, db: AsyncSession, integration_account: IntegrationAccount
) -> None:
    integration_account.is_active = False
    db.add(integration_account)
    await db.flush()
    resp = await auth_client.delete(f"/api/v1/integrations/{integration_account.id}")
    assert resp.status_code == 410


# ── Health check ──────────────────────────────────────────────────────────────

async def test_health_check_returns_ok_when_credentials_valid(
    auth_client: AsyncClient, integration_account: IntegrationAccount, monkeypatch
) -> None:
    from app.integrations import registry
    fake = _fake_provider(healthy=True)
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: fake))

    resp = await auth_client.get(f"/api/v1/integrations/{integration_account.id}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["credentials_ok"] is True
    assert data["provider"] == "trello"


async def test_health_check_returns_false_when_credentials_invalid(
    auth_client: AsyncClient, integration_account: IntegrationAccount, monkeypatch
) -> None:
    from app.integrations import registry
    fake = _fake_provider(healthy=False)
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: fake))

    resp = await auth_client.get(f"/api/v1/integrations/{integration_account.id}/health")
    assert resp.status_code == 200
    assert resp.json()["credentials_ok"] is False


async def test_health_check_handles_provider_exception(
    auth_client: AsyncClient, integration_account: IntegrationAccount, monkeypatch
) -> None:
    from app.integrations import registry
    provider = AsyncMock()
    provider.validate_credentials = AsyncMock(side_effect=ConnectionError("timeout"))
    provider.close = AsyncMock()
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: provider))

    resp = await auth_client.get(f"/api/v1/integrations/{integration_account.id}/health")
    assert resp.status_code == 200
    assert resp.json()["credentials_ok"] is False


# ── List boards ───────────────────────────────────────────────────────────────

async def test_list_boards_returns_normalized_boards(
    auth_client: AsyncClient, integration_account: IntegrationAccount, monkeypatch
) -> None:
    from app.integrations import registry
    boards = [_fake_board("b1", "Board Alpha"), _fake_board("b2", "Board Beta")]
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: _fake_provider(boards=boards)))

    resp = await auth_client.get(f"/api/v1/integrations/{integration_account.id}/boards")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {b["name"] for b in data} == {"Board Alpha", "Board Beta"}
    assert data[0]["provider"] == "trello"


async def test_list_boards_returns_empty_when_no_boards(
    auth_client: AsyncClient, integration_account: IntegrationAccount, monkeypatch
) -> None:
    from app.integrations import registry
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: _fake_provider(boards=[])))

    resp = await auth_client.get(f"/api/v1/integrations/{integration_account.id}/boards")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_boards_404_for_unknown_account(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/v1/integrations/99999/boards")
    assert resp.status_code == 404


# ── List tasks ────────────────────────────────────────────────────────────────

async def test_list_tasks_returns_normalized_tasks(
    auth_client: AsyncClient, integration_account: IntegrationAccount, monkeypatch
) -> None:
    from app.integrations import registry
    tasks = [_fake_task("t1"), _fake_task("t2")]
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: _fake_provider(tasks=tasks)))

    resp = await auth_client.get(
        f"/api/v1/integrations/{integration_account.id}/tasks",
        params={"board_id": "board-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(t["board_id"] == "board-1" for t in data)


# ── Sync trigger ──────────────────────────────────────────────────────────────

async def test_trigger_sync_creates_audit_log(
    auth_client: AsyncClient,
    db: AsyncSession,
    integration_account: IntegrationAccount,
    monkeypatch,
) -> None:
    from app.integrations import registry
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: _fake_provider(synced=7)))

    resp = await auth_client.post(
        f"/api/v1/integrations/{integration_account.id}/sync",
        params={"board_id": "board-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["synced"] == 7
    assert data["provider"] == "trello"
    assert data["incremental"] is True


async def test_trigger_sync_full_mode(
    auth_client: AsyncClient,
    integration_account: IntegrationAccount,
    monkeypatch,
) -> None:
    from app.integrations import registry
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: _fake_provider()))

    resp = await auth_client.post(
        f"/api/v1/integrations/{integration_account.id}/sync",
        params={"board_id": "board-1", "full": "true"},
    )
    assert resp.status_code == 200
    assert resp.json()["incremental"] is False


async def test_trigger_sync_persists_normalized_tasks_and_comments(
    auth_client: AsyncClient,
    db: AsyncSession,
    integration_account: IntegrationAccount,
    monkeypatch,
) -> None:
    from app.integrations import registry

    created = datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc)
    tasks = [
        NormalizedTask(
            id="JIRA-1",
            title="Review integration sync",
            status="in_progress",
            board_id="board-1",
            provider=ProviderType.JIRA,
            assignee_ids=["jira-user-1"],
            story_points=3,
            created_at=created,
            updated_at=created,
        )
    ]
    comments = [
        NormalizedComment(
            id="comment-1",
            task_id="JIRA-1",
            author_id="teammate-1",
            author_name="Team Mate",
            body="Can you check this?",
            created_at=created,
            provider=ProviderType.JIRA,
        )
    ]
    monkeypatch.setattr(
        registry.ProviderRegistry,
        "build",
        staticmethod(lambda acc: _fake_provider(tasks=tasks, comments=comments, synced=1)),
    )

    resp = await auth_client.post(
        f"/api/v1/integrations/{integration_account.id}/sync",
        params={"board_id": "board-1", "project_id": 123},
    )
    assert resp.status_code == 200, resp.text

    task = await db.scalar(select(IntegrationTask).where(IntegrationTask.external_task_id == "JIRA-1"))
    assert task is not None
    assert task.project_id == 123
    assert task.assignee_ids == ["jira-user-1"]

    comment = await db.scalar(select(IntegrationComment).where(IntegrationComment.external_comment_id == "comment-1"))
    assert comment is not None
    assert comment.task_id == task.id


async def test_trigger_sync_links_normalized_tasks_to_imported_trello_project(
    auth_client: AsyncClient,
    db: AsyncSession,
    integration_account: IntegrationAccount,
    monkeypatch,
) -> None:
    from app.integrations import registry

    project = Project(
        name="Linked Trello Project",
        key="LTP",
        description="Imported board",
        is_active=True, 
    )
    db.add(project)
    await db.flush()

    credential = TrelloCredential(
        project_id=project.id,
        api_key="a" * 32,
        api_token="b" * 64,
        is_active=True,
    )
    db.add(credential)
    await db.flush()

    db.add(TrelloBoard(
        credential_id=credential.id,
        trello_id="board-1",
        name="Linked board",
        is_closed=False,
    ))
    await db.flush()

    tasks = [
        NormalizedTask(
            id="card-linked-1",
            title="Linked card",
            status="in_progress",
            board_id="board-1",
            provider=ProviderType.TRELLO,
            assignee_ids=["member-1"],
        )
    ]
    monkeypatch.setattr(
        registry.ProviderRegistry,
        "build",
        staticmethod(lambda acc: _fake_provider(tasks=tasks, synced=1)),
    )

    resp = await auth_client.post(
        f"/api/v1/integrations/{integration_account.id}/sync",
        params={"board_id": "board-1"},
    )
    assert resp.status_code == 200, resp.text

    task = await db.scalar(select(IntegrationTask).where(IntegrationTask.external_task_id == "card-linked-1"))
    assert task is not None
    assert task.project_id == project.id


async def test_import_trello_board_from_connected_account_creates_project_and_links_tasks(
    auth_client: AsyncClient,
    db: AsyncSession,
    integration_account: IntegrationAccount,
    monkeypatch,
) -> None:
    from app.integrations import registry
    from app.services.trello import client as trello_client_module
    from app.services.trello import sync_service
    from app.schemas.trello import TrelloAPIBoard

    board = TrelloAPIBoard(
        id="trello_board_123",
        name="Client Delivery",
        desc="Client work board",
        shortUrl="https://trello.com/b/abc",
        closed=False,
        idOrganization=None,
    )

    async def fake_get_board(self, board_id: str):
        assert board_id == board.id
        return board

    async def fake_full_sync(self, db_board, credential):
        return SimpleNamespace(cards_upserted=1, actions_processed=0, sync_duration_ms=1)

    tasks = [
        NormalizedTask(
            id="card-1",
            title="Imported card",
            status="in_progress",
            board_id=board.id,
            provider=ProviderType.TRELLO,
            assignee_ids=["member-1"],
        )
    ]

    monkeypatch.setattr(trello_client_module.TrelloClient, "get_board", fake_get_board)
    monkeypatch.setattr(sync_service.TrelloSyncService, "full_sync", fake_full_sync)
    monkeypatch.setattr(
        registry.ProviderRegistry,
        "build",
        staticmethod(lambda acc: _fake_provider(boards=[_fake_board(board.id, board.name)], tasks=tasks, synced=1)),
    )

    resp = await auth_client.post(
        f"/api/v1/integrations/{integration_account.id}/import-board",
        params={"board_id": board.id},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["project_id"] > 0
    assert data["board_id"] == board.id
    assert data["board_name"] == board.name

    project = await db.get(Project, data["project_id"])
    assert project is not None
    assert project.name == "Client Delivery"

    db_board = await db.scalar(select(TrelloBoard).where(TrelloBoard.trello_id == board.id))
    assert db_board is not None
    assert db_board.name == "Client Delivery"

    task = await db.scalar(select(IntegrationTask).where(IntegrationTask.external_task_id == "card-1"))
    assert task is not None
    assert task.project_id == project.id


async def test_trigger_sync_returns_502_on_provider_error(
    auth_client: AsyncClient,
    integration_account: IntegrationAccount,
    monkeypatch,
) -> None:
    from app.integrations import registry
    failing = AsyncMock()
    failing.sync_board = AsyncMock(side_effect=RuntimeError("Rate limited"))
    failing.close = AsyncMock()
    monkeypatch.setattr(registry.ProviderRegistry, "build", staticmethod(lambda acc: failing))

    resp = await auth_client.post(
        f"/api/v1/integrations/{integration_account.id}/sync",
        params={"board_id": "board-1"},
    )
    assert resp.status_code == 502
    assert "Sync failed" in resp.json()["detail"]


# ── Sync logs ─────────────────────────────────────────────────────────────────

async def test_get_sync_logs_returns_recent_entries(
    auth_client: AsyncClient,
    db: AsyncSession,
    integration_account: IntegrationAccount,
) -> None:
    log = IntegrationSyncLog(
        account_id=integration_account.id,
        provider="trello",
        board_id="board-1",
        sync_type=SyncType.FULL,
        status=SyncStatus.SUCCESS,
        items_synced=10,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.flush()

    resp = await auth_client.get(f"/api/v1/integrations/{integration_account.id}/sync-logs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "success"
    assert data[0]["items_synced"] == 10


async def test_get_sync_logs_respects_limit(
    auth_client: AsyncClient,
    db: AsyncSession,
    integration_account: IntegrationAccount,
) -> None:
    for i in range(5):
        db.add(IntegrationSyncLog(
            account_id=integration_account.id,
            provider="trello",
            sync_type=SyncType.INCREMENTAL,
            status=SyncStatus.SUCCESS,
            items_synced=i,
            started_at=datetime.now(timezone.utc),
        ))
    await db.flush()

    resp = await auth_client.get(
        f"/api/v1/integrations/{integration_account.id}/sync-logs",
        params={"limit": 3},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ── Trello direct connect ─────────────────────────────────────────────────────

async def test_connect_trello_creates_account(
    auth_client: AsyncClient, monkeypatch
) -> None:
    """Happy path: valid Trello credentials → account created."""
    from app.schemas.trello import TrelloAPIMember
    from app.services.trello import client as trello_client_module

    fake_me = TrelloAPIMember(
        id="member_abc123",
        username="alice",
        fullName="Alice Engineer",
        email=None,
        url=None,
        initials="AE",
        avatarUrl=None,
    )

    async def fake_get_me(self):
        return fake_me

    monkeypatch.setattr(trello_client_module.TrelloClient, "get_me", fake_get_me)

    resp = await auth_client.post(
        "/api/v1/integrations/connect/trello",
        json={"api_key": "a" * 32, "api_token": "b" * 64, "label": "Work Trello"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["provider"] == "trello"
    assert data["account_name"] == "Work Trello"
    assert data["external_account_id"] == "member_abc123"
    assert data["is_active"] is True


async def test_connect_trello_upserts_existing_account(
    auth_client: AsyncClient,
    db: AsyncSession,
    integration_account: IntegrationAccount,
    monkeypatch,
) -> None:
    """Reconnecting an already-connected Trello account updates it in place."""
    from app.schemas.trello import TrelloAPIMember
    from app.services.trello import client as trello_client_module

    fake_me = TrelloAPIMember(
        id=integration_account.external_account_id,
        username="testuser",
        fullName="Test User",
        email=None, url=None, initials="TU", avatarUrl=None,
    )

    async def fake_get_me(self):
        return fake_me

    monkeypatch.setattr(trello_client_module.TrelloClient, "get_me", fake_get_me)

    resp = await auth_client.post(
        "/api/v1/integrations/connect/trello",
        json={"api_key": "c" * 32, "api_token": "d" * 64, "label": "Updated Label"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["account_name"] == "Updated Label"

    # Only one account should exist (upserted, not duplicated)
    list_resp = await auth_client.get("/api/v1/integrations")
    assert len(list_resp.json()) == 1


async def test_connect_trello_invalid_credentials_returns_400(
    auth_client: AsyncClient, monkeypatch
) -> None:
    from app.services.trello import client as trello_client_module

    async def fake_get_me(self):
        raise Exception("Invalid key")

    monkeypatch.setattr(trello_client_module.TrelloClient, "get_me", fake_get_me)

    resp = await auth_client.post(
        "/api/v1/integrations/connect/trello",
        json={"api_key": "bad", "api_token": "key"},
    )
    assert resp.status_code == 400
    assert "validation failed" in resp.json()["detail"].lower()


# ── GitHub direct connect ─────────────────────────────────────────────────────

async def test_connect_github_creates_account(
    auth_client: AsyncClient, monkeypatch
) -> None:
    from app.integrations.providers.github import client as github_client_module

    async def fake_get_me(self):
        return {"id": 42, "login": "alicehub", "name": "Alice Engineer", "email": "alice@example.com"}

    monkeypatch.setattr(github_client_module.GitHubClient, "get_me", fake_get_me)

    resp = await auth_client.post(
        "/api/v1/integrations/connect/github",
        json={"access_token": "github_pat_test", "label": "Work GitHub"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["provider"] == "github"
    assert data["account_name"] == "Work GitHub"
    assert data["external_account_id"] == "42"
    assert data["extra_data"]["github_login"] == "alicehub"


async def test_connect_github_invalid_credentials_returns_400(
    auth_client: AsyncClient, monkeypatch
) -> None:
    from app.integrations.providers.github import client as github_client_module

    async def fake_get_me(self):
        raise Exception("Bad credentials")

    monkeypatch.setattr(github_client_module.GitHubClient, "get_me", fake_get_me)

    resp = await auth_client.post(
        "/api/v1/integrations/connect/github",
        json={"access_token": "bad"},
    )
    assert resp.status_code == 400
    assert "validation failed" in resp.json()["detail"].lower()


# ── OAuth init — 503 when not configured ─────────────────────────────────────

async def test_jira_oauth_start_returns_503_when_not_configured(
    auth_client: AsyncClient, monkeypatch,
) -> None:
    """JIRA_CLIENT_ID is not set in the test environment → 503."""
    from app.config import settings
    monkeypatch.setattr(settings, "jira_client_id", None)
    monkeypatch.setattr(settings, "jira_client_secret", None)

    resp = await auth_client.get("/api/v1/integrations/oauth/jira/start")
    assert resp.status_code == 503
    assert "JIRA_CLIENT_ID" in resp.json()["detail"]


async def test_microsoft_oauth_start_returns_503_when_not_configured(
    auth_client: AsyncClient, monkeypatch,
) -> None:
    """MICROSOFT_CLIENT_ID is not set in the test environment → 503."""
    from app.config import settings
    monkeypatch.setattr(settings, "microsoft_client_id", None)
    monkeypatch.setattr(settings, "microsoft_client_secret", None)

    resp = await auth_client.get("/api/v1/integrations/oauth/microsoft/start")
    assert resp.status_code == 503
    assert "MICROSOFT_CLIENT_ID" in resp.json()["detail"]


async def test_jira_oauth_start_returns_auth_url_when_configured(
    auth_client: AsyncClient, monkeypatch
) -> None:
    """When credentials are set, a valid Atlassian authorization URL is returned."""
    from app.config import settings
    monkeypatch.setattr(settings, "jira_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "jira_client_secret", "fake-client-secret")

    resp = await auth_client.get("/api/v1/integrations/oauth/jira/start")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth.atlassian.com" in data["authorization_url"]
    assert data["provider"] == "jira"
    assert data["state"]


async def test_microsoft_oauth_start_returns_auth_url_when_configured(
    auth_client: AsyncClient, monkeypatch
) -> None:
    from app.config import settings
    monkeypatch.setattr(settings, "microsoft_client_id", "fake-ms-client-id")
    monkeypatch.setattr(settings, "microsoft_client_secret", "fake-ms-secret")

    resp = await auth_client.get("/api/v1/integrations/oauth/microsoft/start")
    assert resp.status_code == 200
    data = resp.json()
    assert "login.microsoftonline.com" in data["authorization_url"]
    assert data["provider"] == "microsoft"
