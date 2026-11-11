"""
Pytest configuration and shared fixtures.

Test DB strategy
────────────────
Each test function gets a fresh SQLite in-memory database created from
SQLAlchemy metadata (Base.metadata.create_all).  The `get_db` FastAPI
dependency is overridden to yield a session backed by this in-memory DB.

The env vars below are set before any app imports so that:
  - pydantic_settings parses them at import time
  - The DATABASE_URL validator passes (postgresql+asyncpg:// scheme)
  - The actual engine in database.py is never used in tests
    (we override get_db completely)
"""
from __future__ import annotations

import os

# ── Must be set before any app.* imports ─────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
os.environ.setdefault("AUTH_ENABLED", "false")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.authz import AuthPrincipal, get_current_principal
# App imports AFTER env vars are set
from app.database import get_db
from app.main import app
from app.models import Base  # triggers all model registrations


# ── Test engine (SQLite in-memory, shared via StaticPool) ─────────────────────

@pytest.fixture(scope="function")
async def test_engine():
    """
    Creates a fresh SQLite in-memory database for each test function.
    StaticPool ensures the single in-memory connection is reused within
    the test, preventing data loss between session operations.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def db(test_engine):
    """Yields an AsyncSession backed by the test SQLite DB."""
    Session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest.fixture(scope="function")
async def client(db: AsyncSession):
    """
    httpx AsyncClient wired to the FastAPI app with the test DB injected.

    The real PostgreSQL engine is never touched because get_db is
    overridden here to yield the SQLite-backed test session.
    """
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    # ASGITransport runs the app without starting a real server.
    # raise_server_exceptions=True surfaces unhandled 500s as test failures.
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.pop(get_db, None)


# ── Data factory helpers ──────────────────────────────────────────────────────

def project_payload(**overrides) -> dict:
    defaults = {
        "name": "Test Project",
        "key": "TST",
        "description": "Integration test project",
        "repository_url": "https://github.com/test/repo",
        "slack_channel": "#test",
    }
    return {**defaults, **overrides}


def sprint_payload(project_id: int, **overrides) -> dict:
    defaults = {
        "project_id": project_id,
        "name": "Sprint 1",
        "goal": "Deliver feature X",
        "start_date": "2026-01-01",
        "end_date": "2026-01-14",
        "committed_points": 40,
    }
    return {**defaults, **overrides}


def ticket_payload(project_id: int, **overrides) -> dict:
    defaults = {
        "project_id": project_id,
        "title": "Implement login page",
        "description": "Build the login form with validation",
        "status": "backlog",
        "priority": "high",
        "ticket_type": "feature",
        "estimated_hours": 8.0,
        "story_points": 5,
    }
    return {**defaults, **overrides}


def developer_payload(**overrides) -> dict:
    defaults = {
        "name": "Alice Engineer",
        "email": "alice@example.com",
        "username": "alice",
        "role": "engineer",
        "team": "backend",
    }
    return {**defaults, **overrides}


# ── User + auth fixtures ──────────────────────────────────────────────────────

@pytest.fixture
async def test_user(db: AsyncSession):
    """Create a test user in the DB and return the ORM object."""
    from app.core.security import hash_password
    from app.models.user import User
    u = User(
        username="testuser",
        email="test@example.com",
        password_hash=hash_password("TestPass123!"),
        is_active=True,
        is_superuser=False,
    )
    db.add(u)
    await db.flush()
    await db.refresh(u)
    return u


@pytest.fixture
async def auth_client(db: AsyncSession, test_user):
    """
    AsyncClient that overrides the `current_user_id` dependency so
    auth-protected endpoints (integrations, etc.) see a real user_id
    without needing a valid JWT Bearer token.
    """
    from app.api.v1.integrations import current_user_id as _cuid

    async def _override_get_db():
        yield db

    async def _override_user_id() -> int:
        return test_user.id

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_cuid] = _override_user_id

    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(_cuid, None)


@pytest.fixture
async def integration_account(db: AsyncSession, test_user):
    """Create a test Trello integration account (tokens pre-encrypted)."""
    from app.integrations.encryption import encrypt_token
    from app.models.integration_account import IntegrationAccount
    account = IntegrationAccount(
        user_id=test_user.id,
        provider="trello",
        account_name="Test Trello",
        external_account_id="member_test_123",
        encrypted_access_token=encrypt_token("fake-api-key-32chars0000000000"),
        encrypted_refresh_token=encrypt_token("fake-api-token-64chars" + "0" * 42),
        scopes=[],
        extra_data={"member_name": "Test User"},
        is_active=True,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


# ── Helper payloads (integration) ─────────────────────────────────────────────

def trello_connect_payload(**overrides) -> dict:
    defaults = {
        "api_key":   "a" * 32,
        "api_token": "b" * 64,
        "label":     "My Trello",
    }
    return {**defaults, **overrides}


# ── Composite fixture: project already created ────────────────────────────────

@pytest.fixture
async def existing_project(client: AsyncClient) -> dict:
    """Creates a project via the API and returns the response JSON."""
    resp = await client.post("/api/v1/projects", json=project_payload())
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def existing_sprint(client: AsyncClient, existing_project: dict) -> dict:
    """Creates an active sprint under existing_project."""
    resp = await client.post(
        "/api/v1/sprints",
        json=sprint_payload(existing_project["id"], status="active"),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def existing_developer(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/developers", json=developer_payload())
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def principal_override():
    def _set(principal: AuthPrincipal):
        async def _override() -> AuthPrincipal:
            return principal

        app.dependency_overrides[get_current_principal] = _override

    yield _set
    app.dependency_overrides.pop(get_current_principal, None)
