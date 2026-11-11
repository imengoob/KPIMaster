"""
Integrations API — connect, manage, and sync external task management providers.

Endpoints
─────────
  GET    /integrations                          — list user's connected accounts
  DELETE /integrations/{account_id}             — disconnect an account
  GET    /integrations/{account_id}/health      — validate credentials + last sync info
  GET    /integrations/{account_id}/boards      — list boards/projects from provider
  GET    /integrations/{account_id}/tasks       — list tasks for a board
  POST   /integrations/tasks                    — create a task via any provider
  PATCH  /integrations/{provider}/tasks/{id}    — update a task via any provider
  POST   /integrations/{account_id}/sync        — trigger full sync for an account
  GET    /integrations/{account_id}/sync-logs   — recent sync audit log

OAuth flows (browser redirect)
─────────────────────────────
  POST    /integrations/oauth/jira/start        — redirect user to Atlassian consent
  GET    /integrations/oauth/jira/callback      — handle Atlassian callback
  GET    /integrations/oauth/microsoft/start    — redirect to Microsoft consent
  GET    /integrations/oauth/microsoft/callback — handle Microsoft callback

Direct connect (API key / token)
─────────────────────────────────
  POST   /integrations/connect/trello           — store Trello API key + token
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
import re

from fastapi.responses import RedirectResponse
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import DbSession
from app.config import settings
from app.integrations.base import NormalizedComment, NormalizedTask, ProviderType, TaskProvider
from app.integrations.encryption import decrypt_token, encrypt_token, safe_decrypt
from app.integrations.registry import ProviderRegistry
from app.models.integration_account import IntegrationAccount
from app.models.integration_sync_log import IntegrationSyncLog, SyncStatus, SyncType
from app.models.integration_task import IntegrationComment, IntegrationTask
from app.models.company import CompanyProjectAccess
from app.models.project import Project
from app.models.trello_credential import TrelloCredential
from app.models.trello_board import TrelloBoard
from app.models.user import User
from app.schemas.integrations import (
    ConnectGitHubRequest,
    ConnectTrelloRequest,
    IntegrationAccountResponse,
    NormalizedBoardResponse,
    NormalizedTaskResponse,
    OAuthInitResponse,
    ProviderHealthResponse,
    SyncLogResponse,
    SyncResultResponse,
    CreateTaskRequest,
    UpdateTaskRequest,
    ImportedProjectResponse,
)
from app.services.trello.client import TrelloClient
from app.services.trello.sync_service import TrelloSyncService
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/integrations", tags=["Integrations"])
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")

# ── Auth dependency ────────────────────────────────────────────────────────────
# Resolves the authenticated user_id from JWT middleware

async def current_user_id(request: Request) -> int:
    uid = getattr(request.state, "auth_user_id", None)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return int(uid)  # JWT sub is stored as str(user.id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid auth token payload")


# ── Account management ────────────────────────────────────────────────────────

@router.get("", response_model=list[IntegrationAccountResponse])
async def list_accounts(
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
    provider:   str | None = Query(None),
    active_only: bool = Query(True),
) -> list[IntegrationAccountResponse]:
    """List all connected integration accounts for the current user."""
    stmt = select(IntegrationAccount).where(IntegrationAccount.user_id == user_id)
    if active_only:
        stmt = stmt.where(IntegrationAccount.is_active.is_(True))
    if provider:
        stmt = stmt.where(IntegrationAccount.provider == provider)
    stmt = stmt.order_by(IntegrationAccount.created_at.desc())
    result = await session.execute(stmt)
    return [_account_to_response(a) for a in result.scalars().all()]


@router.delete("/{account_id}", status_code=204, response_class=Response)
async def disconnect_account(
    account_id: int,
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
) -> Response:
    """Deactivate an integration account (soft delete — preserves audit logs)."""
    account = await _get_account(session, account_id, user_id)
    account.is_active = False
    account.encrypted_access_token  = None
    account.encrypted_refresh_token = None
    session.add(account)
    await session.flush()
    return Response(status_code=204)


@router.get("/{account_id}/health", response_model=ProviderHealthResponse)
async def get_account_health(
    account_id: int,
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
) -> ProviderHealthResponse:
    """Validate credentials and return sync health for an account."""
    account = await _get_account(session, account_id, user_id)
    credentials_ok = False
    try:
        async with ProviderRegistry.open(account) as provider:
            credentials_ok = await provider.validate_credentials()
    except Exception as exc:
        logger.warning("integration.health_check_failed", account_id=account_id, error=str(exc))

    return ProviderHealthResponse(
        account_id=account.id,
        provider=account.provider,
        account_name=account.account_name,
        is_active=account.is_active,
        credentials_ok=credentials_ok,
        last_sync_at=account.last_sync_at,
        token_expires_at=account.token_expires_at,
    )


# ── Boards & Tasks ────────────────────────────────────────────────────────────

@router.get("/{account_id}/boards", response_model=list[NormalizedBoardResponse])
async def list_boards(
    account_id: int,
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
) -> list[NormalizedBoardResponse]:
    account = await _get_account(session, account_id, user_id)
    async with ProviderRegistry.open(account) as provider:
        boards = await provider.get_boards()
    return [
        NormalizedBoardResponse(
            id=b.id, name=b.name, provider=b.provider,
            url=b.url, is_active=b.is_active, extra=b.extra,
        )
        for b in boards
    ]


@router.get("/{account_id}/tasks", response_model=list[NormalizedTaskResponse])
async def list_tasks(
    account_id: int,
    board_id:   str,
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
) -> list[NormalizedTaskResponse]:
    account = await _get_account(session, account_id, user_id)
    async with ProviderRegistry.open(account) as provider:
        tasks = await provider.get_tasks(board_id)
    return [_task_to_response(t) for t in tasks]


@router.post("/tasks", response_model=NormalizedTaskResponse, status_code=201)
async def create_task(
    body:    CreateTaskRequest,
    session: DbSession,
    user_id: int = Depends(current_user_id),
) -> NormalizedTaskResponse:
    account = await _get_account(session, body.account_id, user_id)
    async with ProviderRegistry.open(account) as provider:
        task = await provider.create_task(
            body.board_id,
            {
                "title":        body.title,
                "description":  body.description,
                "priority":     body.priority,
                "task_type":    body.task_type,
                "assignee_id":  body.assignee_id,
                "labels":       body.labels,
                "story_points": body.story_points,
                "due_date":     body.due_date,
            },
        )
    return _task_to_response(task)


@router.patch("/{account_id}/tasks/{task_id}", response_model=NormalizedTaskResponse)
async def update_task(
    account_id: int,
    task_id:    str,
    body:       UpdateTaskRequest,
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
) -> NormalizedTaskResponse:
    account = await _get_account(session, account_id, user_id)
    async with ProviderRegistry.open(account) as provider:
        task = await provider.update_task(task_id, body.model_dump(exclude_none=True))
    return _task_to_response(task)


# ── Manual sync ───────────────────────────────────────────────────────────────

@router.post("/{account_id}/sync", response_model=SyncResultResponse)
async def trigger_sync(
    account_id: int,
    board_id:   str,
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
    full:       bool = Query(False, description="Force full sync (default: incremental)"),
    project_id: int | None = Query(None, description="Optional KPIMaster project to link synced tasks to"),
) -> SyncResultResponse:
    """Trigger a sync for a specific board of this account."""
    account = await _get_account(session, account_id, user_id)
    resolved_project_id = project_id
    if resolved_project_id is None and account.provider == ProviderType.TRELLO.value:
        resolved_project_id = await _resolve_trello_project_id_for_board(session, board_id)

    log = IntegrationSyncLog(
        account_id=account.id,
        provider=account.provider,
        board_id=board_id,
        sync_type=SyncType.FULL if full else SyncType.INCREMENTAL,
        status=SyncStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    session.add(log)
    await session.flush()

    try:
        async with ProviderRegistry.open(account) as provider:
            synced = await provider.sync_board(board_id)
            await _persist_normalized_snapshot(
                session=session,
                account=account,
                provider=provider,
                board_id=board_id,
                project_id=resolved_project_id,
            )

        account.last_sync_at = datetime.now(timezone.utc)
        log.status       = SyncStatus.SUCCESS
        log.items_synced = synced
        log.completed_at = datetime.now(timezone.utc)
        session.add(account)
        session.add(log)

        return SyncResultResponse(
            account_id=account_id,
            board_id=board_id,
            provider=account.provider,
            synced=synced,
            incremental=not full,
        )
    except Exception as exc:
        log.status       = SyncStatus.FAILED
        log.error_detail = str(exc)[:1000]
        log.completed_at = datetime.now(timezone.utc)
        session.add(log)
        raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc


@router.post("/{account_id}/import-board", response_model=ImportedProjectResponse, status_code=201)
async def import_board(
    account_id: int,
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
    board_id:   str = Query(..., description="Board ID to import/link as a KPIMaster project"),
) -> ImportedProjectResponse:
    """
    Import one board from a connected integration account.

    The generic Integrations page can list boards from stored account
    credentials; this endpoint turns one of those boards into a durable
    KPIMaster project and syncs the data used by dashboard pages.
    """
    account = await _get_account(session, account_id, user_id)

    # 1. Fetch the remote board from the generic provider adapter
    try:
        async with ProviderRegistry.open(account) as provider:
            boards = await provider.get_boards()
            api_board = next((b for b in boards if str(b.id) == str(board_id)), None)
            if not api_board:
                raise HTTPException(status_code=404, detail="Board not found on the remote provider.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not load board: {exc}") from exc

    try:
        # 2. Find or create a KPIMaster Project
        existing_projects = await session.execute(select(Project))
        projects = list(existing_projects.scalars().all())
        existing_by_name = {p.name: p for p in projects}
        existing_keys = {p.key for p in projects}
        project = existing_by_name.get(api_board.name)
        if project is None:
            project = Project(
                name=api_board.name,
                key=_project_key_from_board_name(api_board.name, existing_keys, api_board.id),
                description=api_board.extra.get("description", "Imported Project"),
                repository_url=api_board.url or None,
                slack_channel=None,
                is_active=api_board.is_active,
            )
            session.add(project)
            await session.flush()
            await session.refresh(project)
        else:
            project.description = api_board.extra.get("description", project.description)
            project.repository_url = api_board.url or project.repository_url
            project.is_active = api_board.is_active
            await session.flush()

        await _ensure_importing_user_project_access(session, account.user_id, project.id)

        # 3. For backwards compatibility, if Trello, also create Trello-specific tables
        if account.provider == ProviderType.TRELLO.value:
            api_key = safe_decrypt(account.encrypted_access_token) or ""
            api_token = safe_decrypt(account.encrypted_refresh_token) or ""
            if api_key and api_token:
                try:
                    async with TrelloClient(api_key=api_key, api_token=api_token) as client:
                        raw_trello_board = await client.get_board(board_id)
                    credential = await _upsert_project_trello_credential(session, project.id, api_key, api_token)
                    board = await _upsert_project_trello_board(session, credential, raw_trello_board)
                    sync_event = await TrelloSyncService(session).full_sync(board, credential)
                except Exception as t_exc:
                    logger.warning("trello_specific_import_failed", exc_info=t_exc)
        
        # 4. Normalize Snapshot
        async with ProviderRegistry.open(account) as provider:
            normalized_count = await _persist_normalized_snapshot(
                session=session,
                account=account,
                provider=provider,
                board_id=board_id,
                project_id=project.id,
            )

        account.last_sync_at = datetime.now(timezone.utc)
        session.add(IntegrationSyncLog(
            account_id=account.id,
            provider=account.provider,
            board_id=board_id,
            sync_type=SyncType.FULL,
            status=SyncStatus.SUCCESS,
            items_synced=normalized_count,
            errors_count=0,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        ))
        session.add(account)
        await session.commit()

        return ImportedProjectResponse(
            project_id=project.id,
            project_key=project.key,
            board_id=str(api_board.id),
            board_name=api_board.name,
        )
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.exception("integration_import_failed", account_id=account_id, board_id=board_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Failed to save and sync board.",
                "board_id": board_id,
                "account_id": account_id,
            },
        ) from exc
    except Exception as exc:
        await session.rollback()
        logger.exception("integration_import_failed_unexpected", account_id=account_id, board_id=board_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Board import failed: {exc}",
                "board_id": board_id,
                "account_id": account_id,
            },
        ) from exc


@router.get("/{account_id}/sync-logs", response_model=list[SyncLogResponse])
async def get_sync_logs(
    account_id: int,
    session:    DbSession,
    user_id:    int = Depends(current_user_id),
    limit:      int = Query(20, ge=1, le=100),
) -> list[SyncLogResponse]:
    account = await _get_account(session, account_id, user_id)
    stmt = (
        select(IntegrationSyncLog)
        .where(IntegrationSyncLog.account_id == account.id)
        .order_by(IntegrationSyncLog.started_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [SyncLogResponse.model_validate(l) for l in result.scalars().all()]


# ── Direct token connects ─────────────────────────────────────────────────────

@router.post("/connect/trello", response_model=IntegrationAccountResponse, status_code=201)
async def connect_trello(
    body:    ConnectTrelloRequest,
    session: DbSession,
    user_id: int = Depends(current_user_id),
) -> IntegrationAccountResponse:
    """Store Trello API key + token directly (no OAuth redirect needed)."""
    from app.services.trello.client import TrelloClient

    # Validate credentials — get_me() returns a TrelloAPIMember Pydantic model
    try:
        async with TrelloClient(api_key=body.api_key, api_token=body.api_token) as client:
            me = await client.get_me()
            member_id   = me.id
            member_name = me.fullName or me.username or "Trello User"
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Trello credential validation failed: {exc}")

    # Upsert account
    stmt = select(IntegrationAccount).where(
        IntegrationAccount.user_id == user_id,
        IntegrationAccount.provider == "trello",
        IntegrationAccount.external_account_id == member_id,
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        account = IntegrationAccount(
            user_id=user_id,
            provider="trello",
            external_account_id=member_id,
        )

    account.account_name             = body.label or f"Trello — {member_name}"
    account.encrypted_access_token   = encrypt_token(body.api_key)
    account.encrypted_refresh_token  = encrypt_token(body.api_token)
    account.is_active                = True
    account.extra_data               = {"member_name": member_name}
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return _account_to_response(account)


@router.post("/connect/github", response_model=IntegrationAccountResponse, status_code=201)
async def connect_github(
    body:    ConnectGitHubRequest,
    session: DbSession,
    user_id: int = Depends(current_user_id),
) -> IntegrationAccountResponse:
    """Store a GitHub personal access token and expose repositories as boards."""
    from app.integrations.providers.github.client import GitHubClient

    try:
        async with GitHubClient(access_token=body.access_token) as client:
            me = await client.get_me()
            github_id = str(me.get("id") or me.get("login") or "")
            login = str(me.get("login") or "github-user")
            name = str(me.get("name") or login)
            email = me.get("email")
            if not github_id:
                raise ValueError("GitHub profile did not include an id or login.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"GitHub credential validation failed: {exc}")

    stmt = select(IntegrationAccount).where(
        IntegrationAccount.user_id == user_id,
        IntegrationAccount.provider == "github",
        IntegrationAccount.external_account_id == github_id,
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        account = IntegrationAccount(
            user_id=user_id,
            provider="github",
            external_account_id=github_id,
        )

    account.account_name = body.label or f"GitHub — {login}"
    account.encrypted_access_token = encrypt_token(body.access_token)
    account.encrypted_refresh_token = None
    account.scopes = []
    account.token_expires_at = None
    account.is_active = True
    account.extra_data = {
        "github_login": login,
        "display_name": name,
        "user_email": email,
    }
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return _account_to_response(account)


# ── Jira OAuth 2.0 ────────────────────────────────────────────────────────────

@router.post("/oauth/jira/start", response_model=OAuthInitResponse)
async def jira_oauth_start(
    request: Request,
    user_id: int = Depends(current_user_id),
) -> OAuthInitResponse:
    """Return the Atlassian authorization URL. Frontend redirects the user there."""

    from app.integrations.oauth.jira import get_jira_oauth

    body_data = await request.json()
    client_id = body_data.get('client_id')
    secret = body_data.get('client_secret')
    logger.info(
    "integration.connect_attempt",
    client_id=client_id,
    client_secret=secret,
    )
    oauth = get_jira_oauth(client_id , secret)
    state_payload = {
        "user_id": user_id,
        "client_id": client_id,
        "client_secret": secret
    }
    state = _encode_state(state_payload, "jira")


    auth_url, _ = oauth.build_authorization_url(state=state)

    return OAuthInitResponse(
        authorization_url=auth_url, 
        state=state, 
        provider="jira")


@router.get("/oauth/jira/callback")
async def jira_oauth_callback(
    session: DbSession,
    code:    str = Query(...),
    state:   str = Query(...)
) -> RedirectResponse:
    """
    Atlassian redirects here after consent.  Exchanges code → tokens,
    discovers cloud sites, persists encrypted tokens.
    """
    from app.integrations.oauth.jira import get_jira_oauth

    state_data = _decode_state(state, "jira")
        
    user_id = state_data["user_id"]
    client_id = state_data["client_id"]
    client_secret = state_data["client_secret"]
    oauth   = get_jira_oauth(client_id, client_secret)

    try:
        tokens = await oauth.exchange_code(code)
        sites  = await oauth.get_accessible_resources(tokens.access_token)
        if not sites:
            raise HTTPException(status_code=400, detail="No accessible Jira Cloud sites found")

        # Use the first site; in a real app, let the user choose
        site = sites[0]
        cloud_id   = site["id"]
        cloud_name = site.get("name", "Jira Cloud")
        site_url   = site.get("url", "")

        stmt = select(IntegrationAccount).where(
            IntegrationAccount.user_id == user_id,
            IntegrationAccount.provider == "jira",
            IntegrationAccount.external_account_id == cloud_id,
        )
        result  = await session.execute(stmt)
        account = result.scalar_one_or_none()

        if not account:
            account = IntegrationAccount(
                user_id=user_id,
                provider="jira",
                external_account_id=cloud_id,
            )

        account.account_name             = f"Jira — {cloud_name}"
        account.encrypted_access_token   = encrypt_token(tokens.access_token)
        account.encrypted_refresh_token  = (
            encrypt_token(tokens.refresh_token) if tokens.refresh_token else None
        )
        account.token_expires_at = tokens.expires_at
        account.scopes           = tokens.scopes
        account.is_active        = True
        account.extra_data       = {
            "cloud_id":   cloud_id,
            "cloud_name": cloud_name,
            "site_url":   site_url,
        }
        session.add(account)
        await session.flush()

        logger.info("jira.oauth_complete", user_id=user_id, cloud_id=cloud_id)
        return RedirectResponse(url=f"{settings.frontend_url}/integrations?connected=jira")

    except Exception as exc:
        logger.error("jira.oauth_failed", error=str(exc))
        import urllib.parse
        return RedirectResponse(
            url=f"{settings.frontend_url}/integrations?error=jira_oauth_failed&detail={urllib.parse.quote(str(exc))}"
        )


# ── Microsoft OAuth 2.0 ───────────────────────────────────────────────────────

@router.get("/oauth/microsoft/start", response_model=OAuthInitResponse)
async def microsoft_oauth_start(
    user_id: int = Depends(current_user_id),
) -> OAuthInitResponse:
    """Return the Microsoft authorization URL."""
    from app.integrations.oauth.microsoft import get_microsoft_oauth
    oauth = get_microsoft_oauth()
    state = _encode_state(user_id, "microsoft")
    auth_url, _ = oauth.build_authorization_url(state=state)
    return OAuthInitResponse(authorization_url=auth_url, state=state, provider="microsoft")


@router.get("/oauth/microsoft/callback")
async def microsoft_oauth_callback(
    session: DbSession,
    code:    str = Query(...),
    state:   str = Query(...),
) -> RedirectResponse:
    """Handle Microsoft identity platform callback."""
    from app.integrations.oauth.microsoft import get_microsoft_oauth

    user_id = _decode_state(state, "microsoft")
    oauth   = get_microsoft_oauth()

    try:
        tokens  = await oauth.exchange_code(code)
        profile = await oauth.get_user_profile(tokens.access_token)
        ms_user_id = profile.get("id", "")
        display_name = profile.get("displayName", "Microsoft User")
        email = profile.get("mail") or profile.get("userPrincipalName", "")

        stmt = select(IntegrationAccount).where(
            IntegrationAccount.user_id == user_id,
            IntegrationAccount.provider == "microsoft",
            IntegrationAccount.external_account_id == ms_user_id,
        )
        result  = await session.execute(stmt)
        account = result.scalar_one_or_none()

        if not account:
            account = IntegrationAccount(
                user_id=user_id,
                provider="microsoft",
                external_account_id=ms_user_id,
            )

        tenant_id = tokens.extra.get("tenant_id", "common")
        account.account_name             = f"Microsoft — {display_name}"
        account.encrypted_access_token   = encrypt_token(tokens.access_token)
        account.encrypted_refresh_token  = (
            encrypt_token(tokens.refresh_token) if tokens.refresh_token else None
        )
        account.token_expires_at = tokens.expires_at
        account.scopes           = tokens.scopes
        account.is_active        = True
        account.extra_data       = {
            "tenant_id":    tenant_id,
            "user_id":      ms_user_id,
            "user_email":   email,
            "display_name": display_name,
        }
        session.add(account)
        await session.flush()

        logger.info("microsoft.oauth_complete", user_id=user_id, ms_user_id=ms_user_id)
        return RedirectResponse(url=f"{settings.frontend_url}/integrations?connected=microsoft")

    except Exception as exc:
        logger.error("microsoft.oauth_failed", error=str(exc))
        import urllib.parse
        return RedirectResponse(
            url=f"{settings.frontend_url}/integrations?error=ms_oauth_failed&detail={urllib.parse.quote(str(exc))}"
        )


# ── Webhook receivers ─────────────────────────────────────────────────────────

@router.post("/webhooks/jira/{account_id}", status_code=200)
async def receive_jira_webhook(
    account_id: int,
    request:    Request,
    session:    DbSession,
) -> dict[str, str]:
    """
    Receive Jira webhook events.
    Jira sends JSON with webhookEvent, issue, etc.
    Authenticate via shared secret in X-Hub-Signature (future: implement HMAC).
    """
    payload = await request.json()
    event   = payload.get("webhookEvent", "")
    logger.info("jira.webhook_received", account_id=account_id, webhook_event=event)

    # Emit to internal event bus for downstream processors
    # (same pattern as Trello webhooks in the existing codebase)
    # TODO: call event_bus.publish(f"jira.{event}", payload)
    return {"status": "ok"}


@router.post("/webhooks/microsoft/{account_id}", status_code=200)
async def receive_microsoft_webhook(
    account_id:        int,
    request:           Request,
    session:           DbSession,
    validationToken:   str | None = Query(None),
) -> Any:
    """
    Receive Microsoft Graph change notifications.

    Microsoft first sends a validation request with ?validationToken=...
    We must echo it back as plain text with 200.
    """
    if validationToken:
        # Graph subscription validation handshake
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=validationToken, status_code=200)

    payload = await request.json()
    for notification in payload.get("value", []):
        resource = notification.get("resource", "")
        change   = notification.get("changeType", "")
        logger.info(
            "microsoft.webhook_received",
            account_id=account_id,
            resource=resource,
            change=change,
        )
    return {"status": "ok"}


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_account(
    session: AsyncSession, account_id: int, user_id: int
) -> IntegrationAccount:
    result = await session.execute(
        select(IntegrationAccount).where(
            IntegrationAccount.id == account_id,
            IntegrationAccount.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Integration account not found")
    if not account.is_active:
        raise HTTPException(status_code=410, detail="Integration account is disconnected")
    return account


async def _resolve_trello_project_id_for_board(
    session: AsyncSession,
    trello_board_id: str,
) -> int | None:
    result = await session.execute(
        select(TrelloCredential.project_id)
        .join(TrelloBoard, TrelloBoard.credential_id == TrelloCredential.id)
        .where(
            TrelloBoard.trello_id == trello_board_id,
            TrelloCredential.is_active.is_(True),
        )
        .order_by(TrelloBoard.last_synced_at.desc().nullslast(), TrelloBoard.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_or_create_project_for_trello_board(
    session: AsyncSession,
    account: IntegrationAccount,
    api_board: Any,
) -> Project:
    existing_board = await session.scalar(
        select(TrelloBoard).where(TrelloBoard.trello_id == api_board.id)
    )
    if existing_board is not None:
        existing_credential = await session.get(TrelloCredential, existing_board.credential_id)
        if existing_credential is not None:
            project = await session.get(Project, existing_credential.project_id)
            if project is not None:
                project.name = api_board.name
                project.description = api_board.desc or project.description
                project.repository_url = api_board.shortUrl or project.repository_url
                project.is_active = not api_board.closed
                await _ensure_importing_user_project_access(session, account.user_id, project.id)
                await session.flush()
                return project

    existing_projects = await session.execute(select(Project))
    projects = list(existing_projects.scalars().all())
    existing_by_name = {project.name: project for project in projects}
    existing_keys = {project.key for project in projects}
    project = existing_by_name.get(api_board.name)
    if project is None:
        project = Project(
            name=api_board.name,
            key=_project_key_from_board_name(api_board.name, existing_keys, api_board.id),
            description=api_board.desc or "Imported from Trello",
            repository_url=api_board.shortUrl or None,
            slack_channel=None,
            is_active=not api_board.closed,
        )
        session.add(project)
        await session.flush()
        await session.refresh(project)
    else:
        project.description = api_board.desc or project.description
        project.repository_url = api_board.shortUrl or project.repository_url
        project.is_active = not api_board.closed
        await session.flush()

    await _ensure_importing_user_project_access(session, account.user_id, project.id)
    return project


async def _ensure_importing_user_project_access(
    session: AsyncSession,
    user_id: int,
    project_id: int,
) -> None:
    user = await session.get(User, user_id)
    if user is None or user.company_id is None or user.is_superuser:
        return
    existing = await session.scalar(
        select(CompanyProjectAccess).where(
            CompanyProjectAccess.company_id == user.company_id,
            CompanyProjectAccess.project_id == project_id,
        )
    )
    if existing is None:
        session.add(CompanyProjectAccess(company_id=user.company_id, project_id=project_id))
        await session.flush()


async def _upsert_project_trello_credential(
    session: AsyncSession,
    project_id: int,
    api_key: str,
    api_token: str,
) -> TrelloCredential:
    credential = await session.scalar(
        select(TrelloCredential).where(TrelloCredential.project_id == project_id)
    )
    if credential is None:
        credential = TrelloCredential(
            project_id=project_id,
            api_key=api_key,
            api_token=api_token,
            is_active=True,
        )
        session.add(credential)
        await session.flush()
        await session.refresh(credential)
        return credential

    credential.api_key = api_key
    credential.api_token = api_token
    credential.is_active = True
    session.add(credential)
    await session.flush()
    await session.refresh(credential)
    return credential


async def _upsert_project_trello_board(
    session: AsyncSession,
    credential: TrelloCredential,
    api_board: Any,
) -> TrelloBoard:
    board = await session.scalar(
        select(TrelloBoard).where(TrelloBoard.trello_id == api_board.id)
    )
    if board is None:
        board = TrelloBoard(
            credential_id=credential.id,
            trello_id=api_board.id,
            name=api_board.name,
            description=api_board.desc or None,
            short_url=api_board.shortUrl or None,
            trello_org_id=api_board.idOrganization,
            is_closed=api_board.closed,
        )
        session.add(board)
        await session.flush()
        await session.refresh(board)
        return board

    board.credential_id = credential.id
    board.name = api_board.name
    board.description = api_board.desc or None
    board.short_url = api_board.shortUrl or None
    board.trello_org_id = api_board.idOrganization
    board.is_closed = api_board.closed
    session.add(board)
    await session.flush()
    await session.refresh(board)
    return board


def _project_key_from_board_name(name: str, existing_keys: set[str], trello_id: str) -> str:
    normalized = _NON_ALNUM.sub("", name.upper())
    base = (normalized[:6] or "TRL")[:10]
    candidate = base
    suffix = trello_id[-4:].upper()
    counter = 1
    while candidate in existing_keys:
        tail = suffix if counter == 1 else f"{suffix[:2]}{counter:02d}"[-4:]
        candidate = f"{base[:10 - len(tail)]}{tail}"
        counter += 1
    existing_keys.add(candidate)
    return candidate


def _encode_state(data: int, provider: str) -> str:
    """Encode a CSRF-resistant OAuth state token."""
    """Accepts json format """
    import base64
    import hashlib
    import json
    from app.config import settings
    nonce  = secrets.token_hex(16)
    json_to_string = json.dumps(data)
    sig    = hashlib.sha256(f"{nonce}:{json_to_string}:{provider}:{settings.secret_key}".encode()).hexdigest()[:16]
    raw    = f"{nonce}|{provider}|{sig}|{json_to_string}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_state(state: str, expected_provider: str) -> int:
    """Decode and verify the OAuth state. Returns the json containing the user_id, client_id and client_secret."""
    import base64
    import hashlib
    import json
    from app.config import settings
    try:
        raw   = base64.urlsafe_b64decode(state.encode()).decode()
        parts = raw.split("|",3)
        if len(parts) != 4:
            raise ValueError("bad format")
        nonce, provider, sig, data = parts
        expected_sig = hashlib.sha256(
            f"{nonce}:{data}:{provider}:{settings.secret_key}".encode()
        ).hexdigest()[:16]
        
        if sig != expected_sig or provider != expected_provider:
            raise ValueError("signature or provider mismatch")
        return json.loads(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid OAuth state: {exc}") from exc


def _task_to_response(task: Any) -> NormalizedTaskResponse:
    return NormalizedTaskResponse(
        id=task.id, title=task.title, status=task.status,
        board_id=task.board_id, provider=task.provider,
        description=task.description, priority=task.priority,
        task_type=task.task_type, assignee_ids=task.assignee_ids,
        labels=task.labels, story_points=task.story_points,
        due_date=task.due_date, created_at=task.created_at, updated_at=task.updated_at,
    )


def _account_to_response(account: IntegrationAccount) -> IntegrationAccountResponse:
    """Expose useful account metadata without leaking OAuth scopes or raw extras."""
    allowed_extra_keys = {
        "member_name",
        "cloud_name",
        "site_url",
        "tenant_id",
        "user_email",
        "display_name",
        "github_login",
    }
    safe_extra = {
        key: value
        for key, value in (account.extra_data or {}).items()
        if key in allowed_extra_keys and value not in (None, "")
    }
    return IntegrationAccountResponse(
        id=account.id,
        user_id=account.user_id,
        provider=account.provider,
        account_name=account.account_name,
        external_account_id=account.external_account_id,
        is_active=account.is_active,
        last_sync_at=account.last_sync_at,
        token_expires_at=account.token_expires_at,
        scopes=[],
        extra_data=safe_extra,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


async def _persist_normalized_snapshot(
    *,
    session: AsyncSession,
    account: IntegrationAccount,
    provider: TaskProvider,
    board_id: str,
    project_id: int | None,
) -> int:
    """
    Persist provider-normalized tasks and comments for cross-provider KPI queries.

    Provider adapters remain responsible for remote API translation; this layer stores
    the normalized shape so DeveloperKPIService can compute one KPI model across
    Trello, Jira, and Microsoft Planner.
    """
    now = datetime.now(timezone.utc)
    tasks = await provider.get_tasks(board_id)
    seen_ids: set[str] = set()

    for item in tasks:
        db_task = await _upsert_integration_task(
            session=session,
            account=account,
            item=item,
            project_id=project_id,
            now=now,
        )
        seen_ids.add(item.id)

        try:
            comments = await provider.get_comments(item.id)
        except Exception as exc:
            logger.info(
                "integration.comments_unavailable",
                account_id=account.id,
                provider=account.provider,
                task_id=item.id,
                error=str(exc),
            )
            comments = []
        if not isinstance(comments, list):
            comments = []

        for comment in comments:
            await _upsert_integration_comment(
                session=session,
                account=account,
                task=db_task,
                comment=comment,
            )

    if seen_ids:
        result = await session.execute(
            select(IntegrationTask).where(
                IntegrationTask.account_id == account.id,
                IntegrationTask.board_id == board_id,
                IntegrationTask.external_task_id.not_in(seen_ids),
            )
        )
        for stale in result.scalars().all():
            stale.is_active = False
            session.add(stale)

    return len(tasks)


async def _upsert_integration_task(
    *,
    session: AsyncSession,
    account: IntegrationAccount,
    item: NormalizedTask,
    project_id: int | None,
    now: datetime,
) -> IntegrationTask:
    result = await session.execute(
        select(IntegrationTask).where(
            IntegrationTask.account_id == account.id,
            IntegrationTask.board_id == item.board_id,
            IntegrationTask.external_task_id == item.id,
        )
    )
    db_task = result.scalar_one_or_none()
    if db_task is None:
        db_task = IntegrationTask(
            account_id=account.id,
            provider=str(item.provider.value if hasattr(item.provider, "value") else item.provider),
            board_id=item.board_id,
            external_task_id=item.id,
        )

    db_task.project_id = project_id if project_id is not None else db_task.project_id
    db_task.provider = str(item.provider.value if hasattr(item.provider, "value") else item.provider)
    db_task.title = item.title
    db_task.status = item.status
    db_task.description = item.description
    db_task.priority = item.priority
    db_task.task_type = item.task_type or "task"
    db_task.assignee_ids = list(item.assignee_ids or [])
    db_task.labels = list(item.labels or [])
    db_task.story_points = item.story_points
    db_task.due_date = item.due_date
    db_task.external_created_at = item.created_at
    db_task.external_updated_at = item.updated_at
    db_task.last_synced_at = now
    db_task.is_active = True
    db_task.raw = item.raw or {}
    session.add(db_task)
    await session.flush()
    return db_task


async def _upsert_integration_comment(
    *,
    session: AsyncSession,
    account: IntegrationAccount,
    task: IntegrationTask,
    comment: NormalizedComment,
) -> IntegrationComment:
    external_comment_id = comment.id or f"{comment.task_id}:{comment.author_id}:{comment.created_at.isoformat()}"
    result = await session.execute(
        select(IntegrationComment).where(
            IntegrationComment.account_id == account.id,
            IntegrationComment.external_comment_id == external_comment_id,
        )
    )
    db_comment = result.scalar_one_or_none()
    if db_comment is None:
        db_comment = IntegrationComment(
            account_id=account.id,
            task_id=task.id,
            provider=str(comment.provider.value if hasattr(comment.provider, "value") else comment.provider),
            external_comment_id=external_comment_id,
            external_task_id=task.external_task_id,
        )

    db_comment.task_id = task.id
    db_comment.provider = str(comment.provider.value if hasattr(comment.provider, "value") else comment.provider)
    db_comment.external_task_id = task.external_task_id
    db_comment.author_external_id = comment.author_id or ""
    db_comment.author_name = comment.author_name or ""
    db_comment.body = comment.body or ""
    db_comment.external_created_at = comment.created_at
    db_comment.raw = {}
    session.add(db_comment)
    await session.flush()
    return db_comment
