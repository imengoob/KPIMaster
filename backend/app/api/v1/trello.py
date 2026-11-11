"""
Trello integration API — /api/v1/trello

Endpoints
─────────
POST   /trello/connect                    Connect a project to Trello (store credentials + run full sync)
GET    /trello/boards                     List all boards for the authed project
GET    /trello/boards/{board_id}          Board detail
POST   /trello/boards/{board_id}/sync     Trigger incremental sync (or full if ?full=true)
GET    /trello/boards/{board_id}/lists    Board lists with card counts
GET    /trello/boards/{board_id}/cards    Cards on a board (filterable by list_type, is_stalled)
GET    /trello/boards/{board_id}/analytics  Board analytics (cycle time, throughput, WIP, blockers)

POST   /trello/boards/{board_id}/webhooks          Register Trello webhook for a board
DELETE /trello/boards/{board_id}/webhooks/{wh_id}  Deregister webhook

POST   /trello/webhooks/{trello_webhook_id}/receive  Trello callback endpoint (HMAC-verified)
HEAD   /trello/webhooks/{trello_webhook_id}/receive  Trello HEAD probe (returns 200)

PATCH  /trello/lists/{list_id}/type       Override list type classification

Authentication note
───────────────────
The project-level `api_key` / `api_token` are stored in `trello_credentials`.
They are loaded from the database for every request — never taken from headers.
"""
from __future__ import annotations

import re
from typing import Annotated
from urllib.parse import parse_qs, urlparse

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access, require_roles
from app.api.dependencies import DbSession
from app.config import settings
from app.core.logging_config import get_logger
from app.models.company import CompanyProjectAccess
from app.models.project import Project
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard
from app.models.trello_credential import TrelloCredential
from app.models.trello_list import ListType, TrelloList
from app.models.trello_webhook import TrelloWebhook
from app.models.trello_app_settings import TrelloAppSettings
from app.schemas.trello import (
    AvailableTrelloBoardRead,
    BoardSummaryResponse,
    BoardListSummaryItem,
    ConnectTrelloRequest,
    ImportedTrelloProjectRead,
    ImportTrelloBoardsRequest,
    ListTypeOverrideRequest,
    ReclassifyListsResponse,
    RegisterWebhookRequest,
    SaveTrelloSettingsRequest,
    ProjectCommentMetricsRead,
    TicketCommentInsightRead,
    TrelloAnalytics,
    TrelloAppSettingsRead,
    TrelloBoardRead,
    TrelloCardRead,
    TrelloListRead,
    TrelloWebhookRead,
)
from app.services.trello.analytics_service import TrelloAnalyticsService
from app.services.trello.comment_analysis_service import TrelloCommentAnalysisService
from app.services.trello.client import TrelloClient
from app.services.trello.sync_service import TrelloSyncService, classify_list
from app.services.trello.webhook_service import TrelloWebhookService

logger = get_logger(__name__)

router = APIRouter(prefix="/trello", tags=["Trello"])
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


# ── Dependency helpers ────────────────────────────────────────────────────────

def _get_ws_manager(request: Request):
    return request.app.state.ws_manager


async def _load_board(board_id: int, session: AsyncSession) -> TrelloBoard:
    board = await session.get(TrelloBoard, board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found.")
    return board


async def _load_credential_for_board(board: TrelloBoard, session: AsyncSession) -> TrelloCredential:
    cred = await session.get(TrelloCredential, board.credential_id)
    if not cred or not cred.is_active:
        raise HTTPException(status_code=404, detail="No active Trello credential for this board.")
    return cred


def _sanitize_credential(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().lstrip(":=").strip()
    value = value.strip("\"'")
    return value or None


def _normalize_trello_token(raw: str | None) -> str | None:
    value = _sanitize_credential(raw)
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        query_token = parse_qs(parsed.query).get("token")
        if query_token and query_token[0].strip():
            return _sanitize_credential(query_token[0])
    token_match = re.search(r"(?:^|[?&#])token=([^&#\s]+)", value, flags=re.IGNORECASE)
    if token_match:
        return _sanitize_credential(token_match.group(1))
    return value


def _resolve_credentials(api_key: str | None, api_token: str | None) -> tuple[str, str]:
    resolved_key = _sanitize_credential(api_key) or _sanitize_credential(settings.trello_api_key)
    resolved_token = _normalize_trello_token(api_token) or _normalize_trello_token(settings.trello_api_token)
    if not resolved_key or not resolved_token:
        raise HTTPException(
            status_code=400,
            detail=(
                "Trello credentials are missing. Set TRELLO_API_KEY and TRELLO_API_TOKEN "
                "on the backend or provide them in the request."
            ),
        )
    return resolved_key, resolved_token


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


async def _upsert_board(
    session: AsyncSession,
    credential: TrelloCredential,
    api_board,
) -> TrelloBoard:
    result = await session.execute(
        select(TrelloBoard).where(TrelloBoard.trello_id == api_board.id)
    )
    board = result.scalar_one_or_none()
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
    await session.flush()
    await session.refresh(board)
    return board


# ── App-level settings (singleton) ───────────────────────────────────────────

@router.get("/settings", response_model=TrelloAppSettingsRead)
async def get_trello_settings(session: DbSession, principal: CurrentPrincipal) -> TrelloAppSettingsRead:
    """
    Return the saved Trello credentials and selected board IDs for the current company.
    Returns has_credentials=False with empty strings when nothing is saved yet.
    """
    if principal.company_id is None:
        raise HTTPException(status_code=403, detail="No company associated.")
        
    result = await session.execute(
        select(TrelloAppSettings).where(TrelloAppSettings.company_id == principal.company_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return TrelloAppSettingsRead(
            has_credentials=False,
            api_key="",
            api_token="",
            selected_board_ids=[],
        )
    return TrelloAppSettingsRead(
        has_credentials=True,
        api_key=row.api_key,
        api_token=row.api_token,
        selected_board_ids=list(row.selected_board_ids or []),
    )


@router.post("/settings", response_model=TrelloAppSettingsRead, status_code=200)
async def save_trello_settings(
    body: SaveTrelloSettingsRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> TrelloAppSettingsRead:
    """
    Persist Trello credentials and selected board IDs for the current company.
    Does NOT trigger any sync — call /import-boards to sync.
    Uses UPSERT so the table stays a single row per company.
    """
    if principal.company_id is None:
        raise HTTPException(status_code=403, detail="No company associated.")

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    api_key = _sanitize_credential(body.api_key) or _sanitize_credential(settings.trello_api_key) or ""
    api_token = _normalize_trello_token(body.api_token) or _normalize_trello_token(settings.trello_api_token) or ""

    if not api_key or not api_token:
        raise HTTPException(
            status_code=400,
            detail="Provide api_key and api_token, or set TRELLO_API_KEY / TRELLO_API_TOKEN in the backend env.",
        )
    
    # We omit 'id' to let it auto-increment, and use company_id for upsert
    stmt = (
        pg_insert(TrelloAppSettings)
        .values(
            company_id=principal.company_id,
            api_key=api_key,
            api_token=api_token,
            selected_board_ids=body.selected_board_ids,
        )
        .on_conflict_do_update(
            index_elements=["company_id"],
            set_={
                "api_key": api_key,
                "api_token": api_token,
                "selected_board_ids": body.selected_board_ids,
                "updated_at": sa.func.now(),
            },
        )
    )
    await session.execute(stmt)
    await session.commit()

    result = await session.execute(
        select(TrelloAppSettings).where(TrelloAppSettings.company_id == principal.company_id)
    )
    row = result.scalar_one_or_none()
    return TrelloAppSettingsRead(
        has_credentials=True,
        api_key=row.api_key,
        api_token=row.api_token,
        selected_board_ids=list(row.selected_board_ids or []),
    )


# ── Connect ───────────────────────────────────────────────────────────────────

@router.post("/connect", status_code=201)
async def connect_trello(
    body: ConnectTrelloRequest,
    session: DbSession,
    request: Request,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
        )
    ),
):
    """
    Store Trello API credentials for a project and run an initial full sync
    on all boards accessible with those credentials.

    Returns a list of synced board summaries.
    """
    await ensure_project_access(session, principal, body.project_id)
    # Validate credentials by fetching the member's boards
    api_key, api_token = _resolve_credentials(body.api_key, body.api_token)
    import httpx
    async with TrelloClient(api_key=api_key, api_token=api_token) as client:
        try:
            api_boards = await client.get_my_boards()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=f"Invalid Trello credentials or unauthorized: {exc}")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Trello API unreachable: {exc}")

    # Upsert credential row
    existing_cred = await session.scalar(
        select(TrelloCredential).where(TrelloCredential.project_id == body.project_id)
    )
    if existing_cred:
        existing_cred.api_key = api_key
        existing_cred.api_token = api_token
        existing_cred.is_active = True
        credential = existing_cred
    else:
        credential = TrelloCredential(
            project_id=body.project_id,
            api_key=api_key,
            api_token=api_token,
            is_active=True,
        )
        session.add(credential)
    await session.flush()

    # Create/upsert board rows
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    board_values = [
        {
            "credential_id": credential.id,
            "trello_id": b.id,
            "name": b.name,
            "description": b.desc or None,
            "short_url": b.shortUrl or None,
            "is_closed": b.closed,
        }
        for b in api_boards
    ]
    stmt = pg_insert(TrelloBoard).values(board_values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["trello_id"],
        set_={
            "name": stmt.excluded.name,
            "credential_id": stmt.excluded.credential_id,
            "is_closed": stmt.excluded.is_closed,
        },
    ).returning(TrelloBoard.id, TrelloBoard.trello_id, TrelloBoard.name)
    result = await session.execute(stmt)
    board_rows = result.fetchall()

    # Kick off full sync for each board
    sync_svc = TrelloSyncService(session)
    synced = []
    try:
        for row in board_rows:
            board = await session.get(TrelloBoard, row.id)
            if board:
                await sync_svc.full_sync(board, credential)
                synced.append({"id": row.id, "trello_id": row.trello_id, "name": row.name})
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.exception("trello_connect_sync_failed", project_id=body.project_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=(
                "Connected to Trello, but syncing board data into KPIMaster failed. "
                "Please retry after restarting the backend so the latest sync fixes are loaded."
            ),
        ) from exc

    await session.commit()
    return {"connected": True, "boards_synced": synced}

@router.post("/available-boards", response_model=list[AvailableTrelloBoardRead], status_code=200)
async def list_available_trello_boards(
    body: ImportTrelloBoardsRequest,
) -> list[AvailableTrelloBoardRead]:
    """
    Validate Trello credentials and return accessible boards without syncing them.
    """
    api_key, api_token = _resolve_credentials(body.api_key, body.api_token)

    async with TrelloClient(api_key=api_key, api_token=api_token) as client:
        try:
            api_boards = await client.get_my_boards()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=f"Invalid Trello credentials or unauthorized: {exc}")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Trello API unreachable: {exc}")

    selected_board_ids = {board_id.strip() for board_id in body.board_ids if board_id.strip()}
    if selected_board_ids:
        api_boards = [board for board in api_boards if board.id in selected_board_ids]
        if not api_boards:
            raise HTTPException(status_code=404, detail="No accessible Trello boards matched the requested board IDs.")

    return [
        AvailableTrelloBoardRead(
            id=board.id,
            name=board.name,
            description=board.desc or None,
            short_url=board.shortUrl or None,
            is_closed=board.closed,
            organization_id=board.idOrganization,
        )
        for board in api_boards
    ]


@router.post("/import-boards", response_model=list[ImportedTrelloProjectRead], status_code=201)
async def import_trello_boards(
    body: ImportTrelloBoardsRequest,
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
        )
    ),
) -> list[ImportedTrelloProjectRead]:
    """
    Import Trello boards into the local project catalog and sync their live data.
    """
    api_key, api_token = _resolve_credentials(body.api_key, body.api_token)

    async with TrelloClient(api_key=api_key, api_token=api_token) as client:
        try:
            api_boards = await client.get_my_boards()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=f"Invalid Trello credentials or unauthorized: {exc}")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Trello API unreachable: {exc}")

    selected_board_ids = {board_id.strip() for board_id in body.board_ids if board_id.strip()}
    if selected_board_ids:
        api_boards = [board for board in api_boards if board.id in selected_board_ids]
        if not api_boards:
            raise HTTPException(status_code=404, detail="No accessible Trello boards matched the requested board IDs.")

    existing_projects = await session.execute(select(Project))
    existing_by_name = {project.name: project for project in existing_projects.scalars().all()}
    existing_keys = {project.key for project in existing_by_name.values()}

    imported: list[ImportedTrelloProjectRead] = []
    sync_svc = TrelloSyncService(session)

    try:
        for api_board in api_boards:
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
                if principal.company_id is not None and not principal.is_superuser:
                    session.add(CompanyProjectAccess(company_id=principal.company_id, project_id=project.id))
                existing_by_name[project.name] = project
            else:
                project.description = api_board.desc or project.description
                project.repository_url = api_board.shortUrl or project.repository_url
                project.is_active = not api_board.closed
                await session.flush()
                if principal.company_id is not None and not principal.is_superuser:
                    existing_link = await session.scalar(
                        select(CompanyProjectAccess).where(
                            CompanyProjectAccess.company_id == principal.company_id,
                            CompanyProjectAccess.project_id == project.id,
                        )
                    )
                    if existing_link is None:
                        session.add(CompanyProjectAccess(company_id=principal.company_id, project_id=project.id))

            result = await session.execute(
                select(TrelloCredential).where(TrelloCredential.project_id == project.id)
            )
            credential = result.scalar_one_or_none()
            if credential is None:
                credential = TrelloCredential(
                    project_id=project.id,
                    api_key=api_key,
                    api_token=api_token,
                    is_active=True,
                )
                session.add(credential)
                await session.flush()
                await session.refresh(credential)
            else:
                credential.api_key = api_key
                credential.api_token = api_token
                credential.is_active = True
                await session.flush()

            board = await _upsert_board(session, credential, api_board)
            await sync_svc.full_sync(board, credential)
            imported.append(
                ImportedTrelloProjectRead(
                    project_id=project.id,
                    project_key=project.key,
                    board_id=board.id,
                    board_name=board.name,
                    trello_board_id=board.trello_id,
                    short_url=board.short_url,
                )
            )
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.exception("trello_import_sync_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=(
                "Trello authentication succeeded, but KPIMaster failed while saving board data. "
                "Restart the backend to load the latest sync fixes, then try the import again."
            ),
        ) from exc

    await session.commit()
    return imported


# ── Boards ────────────────────────────────────────────────────────────────────

@router.get("/boards", response_model=list[TrelloBoardRead])
async def list_boards(
    session: DbSession,
    project_id: int = Query(..., description="Project to list boards for"),
):
    result = await session.execute(
        select(TrelloBoard)
        .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
        .where(TrelloCredential.project_id == project_id, TrelloCredential.is_active.is_(True))
        .order_by(TrelloBoard.name)
    )
    boards = result.scalars().all()

    # Annotate with counts
    reads = []
    for b in boards:
        list_count = await session.scalar(
            select(func.count(TrelloList.id)).where(TrelloList.board_id == b.id)
        )
        card_count = await session.scalar(
            select(func.count(TrelloCard.id)).where(
                TrelloCard.board_id == b.id, TrelloCard.is_closed.is_(False)
            )
        )
        r = TrelloBoardRead.model_validate(b)
        r = r.model_copy(update={"list_count": list_count or 0, "card_count": card_count or 0})
        reads.append(r)

    return reads


@router.get("/boards/{board_id}", response_model=TrelloBoardRead)
async def get_board(board_id: int, session: DbSession):
    board = await _load_board(board_id, session)
    list_count = await session.scalar(
        select(func.count(TrelloList.id)).where(TrelloList.board_id == board_id)
    )
    card_count = await session.scalar(
        select(func.count(TrelloCard.id)).where(
            TrelloCard.board_id == board_id, TrelloCard.is_closed.is_(False)
        )
    )
    r = TrelloBoardRead.model_validate(board)
    return r.model_copy(update={"list_count": list_count or 0, "card_count": card_count or 0})


@router.post("/boards/{board_id}/sync", status_code=202)
async def sync_board(
    board_id: int,
    session: DbSession,
    full: bool = Query(False, description="Force a full sync instead of incremental"),
):
    """Trigger sync. Returns immediately with accepted; sync runs in-request (consider moving to Celery for large boards)."""
    board = await _load_board(board_id, session)
    credential = await _load_credential_for_board(board, session)
    svc = TrelloSyncService(session)

    if full or board.last_action_id is None:
        event = await svc.full_sync(board, credential)
    else:
        event = await svc.incremental_sync(board, credential)

    await session.commit()
    return {
        "status": "synced",
        "cards_upserted": event.cards_upserted,
        "actions_processed": event.actions_processed,
        "duration_ms": round(event.sync_duration_ms),
    }


@router.post("/projects/{project_id}/sync", status_code=200)
async def sync_project_boards(
    project_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
    full: bool = Query(False, description="Force full sync instead of incremental"),
):
    """
    Sync all Trello boards linked to a project in one call.

    This is what the frontend Refresh button should call so that newly assigned
    cards, member changes, and list moves are pulled from Trello before the UI
    re-fetches its data.
    """
    await ensure_project_access(session, principal, project_id)
    # Find all active boards for this project
    result = await session.execute(
        select(TrelloBoard, TrelloCredential)
        .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
        .where(
            TrelloCredential.project_id == project_id,
            TrelloCredential.is_active.is_(True),
        )
        .order_by(TrelloBoard.id)
    )
    rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No active Trello boards found for this project. Import a board first.",
        )

    svc = TrelloSyncService(session)
    summary: list[dict] = []

    for board, credential in rows:
        try:
            if full or board.last_action_id is None:
                event = await svc.full_sync(board, credential)
            else:
                event = await svc.incremental_sync(board, credential)

            summary.append({
                "board_id": board.id,
                "board_name": board.name,
                "status": "synced",
                "cards_upserted": event.cards_upserted,
                "actions_processed": event.actions_processed,
                "duration_ms": round(event.sync_duration_ms),
            })
        except Exception as exc:
            logger.warning(
                "project_sync_board_failed",
                project_id=project_id,
                board_id=board.id,
                error=str(exc),
            )
            summary.append({
                "board_id": board.id,
                "board_name": board.name,
                "status": "error",
                "error": str(exc),
            })

    await session.commit()
    synced = sum(1 for s in summary if s["status"] == "synced")
    return {
        "project_id": project_id,
        "boards_synced": synced,
        "boards_total": len(rows),
        "results": summary,
    }


# ── Board-level summary & reclassify ─────────────────────────────────────────

@router.get("/projects/{project_id}/comment-insights", response_model=ProjectCommentMetricsRead)
async def get_project_comment_insights(
    project_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
) -> ProjectCommentMetricsRead:
    """
    Analyze Trello ticket comments for the project's primary board and return
    structured blocker, sentiment, response-time, and communication insights.
    """
    await ensure_project_access(session, principal, project_id)
    try:
        return await TrelloCommentAnalysisService(session).analyze_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/tickets/{ticket_id}/comment-insights",
    response_model=TicketCommentInsightRead,
)
async def get_ticket_comment_insights(
    project_id: int,
    ticket_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
) -> TicketCommentInsightRead:
    """
    Analyze the comment thread for a single Trello-backed ticket.
    """
    await ensure_project_access(session, principal, project_id)
    try:
        return await TrelloCommentAnalysisService(session).analyze_ticket(project_id, ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/projects/{project_id}/board-summary", response_model=BoardSummaryResponse)
async def get_project_board_summary(
    project_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
) -> BoardSummaryResponse:
    from dateutil.parser import parse as parse_date
    """
    Return per-list card counts and derived KPIs for the primary board of a project.
    The frontend uses this to show a list-aware progress breakdown.
    """
    await ensure_project_access(session, principal, project_id)
    result = await session.execute(
        select(TrelloBoard, TrelloCredential)
        .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
        .where(
            TrelloCredential.project_id == project_id,
            TrelloCredential.is_active.is_(True),
        )
        .order_by(TrelloBoard.last_synced_at.desc().nullslast(), TrelloBoard.id.asc())
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="No active Trello board found for this project.")

    board: TrelloBoard = row[0]

    lists_result = await session.execute(
        select(TrelloList).where(TrelloList.board_id == board.id).order_by(TrelloList.pos)
    )
    lists = lists_result.scalars().all()

    items: list[BoardListSummaryItem] = []
    total = backlog = wip = done = 0

    for lst in lists:
        stmt = select(func.count(TrelloCard.id)).where(
            TrelloCard.list_id == lst.id, TrelloCard.is_closed.is_(False)
        )
        if start_date:
            stmt = stmt.where(TrelloCard.trello_last_activity >= parse_date(start_date))
        if end_date:
            stmt = stmt.where(TrelloCard.trello_last_activity <= parse_date(end_date))
        count = await session.scalar(stmt) or 0
        ltype = lst.list_type.value if lst.list_type else "unknown"
        items.append(BoardListSummaryItem(
            list_id=lst.id,
            name=lst.name,
            list_type=ltype,
            card_count=count,
            position=float(lst.pos or 0),
        ))
        total += count
        if ltype == "backlog":
            backlog += count
        elif ltype == "wip":
            wip += count
        elif ltype == "done":
            done += count

    completion_rate = round(done / total, 4) if total else 0.0

    return BoardSummaryResponse(
        project_id=project_id,
        board_id=board.id,
        board_name=board.name,
        lists=items,
        total_cards=total,
        backlog_count=backlog,
        wip_count=wip,
        done_count=done,
        completion_rate=completion_rate,
    )


@router.post("/boards/{board_id}/reclassify-lists", response_model=ReclassifyListsResponse, status_code=200)
async def reclassify_board_lists(board_id: int, session: DbSession) -> ReclassifyListsResponse:
    """
    Re-apply auto-classification rules to all lists on a board and save the result.

    Use this after updating the classification patterns so existing lists get
    their list_type refreshed without requiring a full Trello API sync.
    """
    await _load_board(board_id, session)

    lists_result = await session.execute(
        select(TrelloList).where(TrelloList.board_id == board_id).order_by(TrelloList.pos)
    )
    lists = lists_result.scalars().all()

    updated = []
    for lst in lists:
        new_type = classify_list(lst.name)
        old_type = lst.list_type
        lst.list_type = new_type
        updated.append({
            "list_id": lst.id,
            "name": lst.name,
            "old_type": old_type.value if old_type else "unknown",
            "new_type": new_type.value,
        })

    await session.flush()
    await session.commit()

    return ReclassifyListsResponse(
        board_id=board_id,
        lists_updated=len(updated),
        lists=updated,
    )


# ── Lists ─────────────────────────────────────────────────────────────────────

@router.get("/boards/{board_id}/lists", response_model=list[TrelloListRead])
async def get_board_lists(board_id: int, session: DbSession):
    await _load_board(board_id, session)
    result = await session.execute(
        select(TrelloList).where(TrelloList.board_id == board_id).order_by(TrelloList.pos)
    )
    lists = result.scalars().all()

    reads = []
    for lst in lists:
        count = await session.scalar(
            select(func.count(TrelloCard.id)).where(
                TrelloCard.list_id == lst.id, TrelloCard.is_closed.is_(False)
            )
        )
        r = TrelloListRead.model_validate(lst)
        reads.append(r.model_copy(update={"card_count": count or 0}))
    return reads


@router.patch("/lists/{list_id}/type", response_model=TrelloListRead)
async def override_list_type(
    list_id: int,
    body: ListTypeOverrideRequest,
    session: DbSession,
):
    """Manually override the auto-classified list type."""
    lst = await session.get(TrelloList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found.")
    lst.list_type = body.list_type
    await session.flush()
    await session.commit()
    return TrelloListRead.model_validate(lst)


# ── Cards ─────────────────────────────────────────────────────────────────────

@router.get("/boards/{board_id}/cards", response_model=list[TrelloCardRead])
async def get_board_cards(
    board_id: int,
    session: DbSession,
    list_type: ListType | None = Query(None, description="Filter by list type"),
    stalled_only: bool = Query(False, description="Only return stalled cards"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    await _load_board(board_id, session)

    q = (
        select(TrelloCard, TrelloList)
        .join(TrelloList, TrelloCard.list_id == TrelloList.id, isouter=True)
        .where(TrelloCard.board_id == board_id, TrelloCard.is_closed.is_(False))
    )
    if list_type:
        q = q.where(TrelloList.list_type == list_type)
    if stalled_only:
        q = q.where(TrelloCard.is_stalled.is_(True))

    q = q.order_by(TrelloCard.trello_short_id).limit(limit).offset(offset)
    result = await session.execute(q)
    rows = result.all()

    reads = []
    for card, lst in rows:
        r = TrelloCardRead.model_validate(card)
        r = r.model_copy(
            update={
                "list_name": lst.name if lst else None,
                "list_type": lst.list_type if lst else None,
            }
        )
        reads.append(r)
    return reads


# ── Analytics ─────────────────────────────────────────────────────────────────

@router.get("/boards/{board_id}/analytics", response_model=TrelloAnalytics)
async def get_board_analytics(
    board_id: int,
    session: DbSession,
    request: Request,
    throughput_days: int = Query(7, ge=1, le=90, description="Throughput window in days"),
):
    board = await _load_board(board_id, session)
    ws_manager = _get_ws_manager(request)

    svc = TrelloAnalyticsService(session, ws_manager)
    analytics = await svc.compute_board_analytics(board, throughput_days=throughput_days)
    await session.commit()
    return analytics


# ── Webhooks ──────────────────────────────────────────────────────────────────

@router.post("/boards/{board_id}/webhooks", response_model=TrelloWebhookRead, status_code=201)
async def register_webhook(
    board_id: int,
    body: RegisterWebhookRequest,
    session: DbSession,
    request: Request,
):
    board = await _load_board(board_id, session)
    credential = await _load_credential_for_board(board, session)
    ws_manager = _get_ws_manager(request)

    svc = TrelloWebhookService(session, ws_manager)
    webhook = await svc.register_webhook(
        board=board,
        credential=credential,
        callback_url=body.callback_url,
        description=body.description,
    )
    await session.commit()
    return TrelloWebhookRead.model_validate(webhook)


@router.delete("/boards/{board_id}/webhooks/{webhook_id}", status_code=204)
async def deregister_webhook(
    board_id: int,
    webhook_id: int,
    session: DbSession,
    request: Request,
):
    board = await _load_board(board_id, session)
    credential = await _load_credential_for_board(board, session)

    webhook = await session.scalar(
        select(TrelloWebhook).where(
            TrelloWebhook.id == webhook_id,
            TrelloWebhook.board_id == board.id,
        )
    )
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found.")

    ws_manager = _get_ws_manager(request)
    svc = TrelloWebhookService(session, ws_manager)
    await svc.deregister_webhook(webhook, credential)
    await session.commit()
    return Response(status_code=204)


# ── Trello callback endpoints ─────────────────────────────────────────────────

@router.head("/webhooks/{trello_webhook_id}/receive", status_code=200)
async def trello_webhook_probe(trello_webhook_id: str):
    """
    Trello sends a HEAD request when a webhook is first registered.
    Must respond 200 for the registration to succeed.
    """
    return Response(status_code=200)


@router.post("/webhooks/{trello_webhook_id}/receive", status_code=200)
async def trello_webhook_receive(
    trello_webhook_id: str,
    request: Request,
    session: DbSession,
):
    """
    Receive and process Trello webhook payloads.

    Security: verifies HMAC-SHA1 signature using the stored api_key.
    Trello sends the signature in the `x-trello-webhook` header.
    """
    # Load the webhook record
    webhook = await session.scalar(
        select(TrelloWebhook).where(
            TrelloWebhook.trello_webhook_id == trello_webhook_id,
            TrelloWebhook.is_active.is_(True),
        )
    )
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not registered.")

    board = await session.get(TrelloBoard, webhook.board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found.")

    credential = await session.get(TrelloCredential, board.credential_id)
    if not credential:
        raise HTTPException(status_code=403, detail="No credential for this board.")

    # Verify HMAC-SHA1 signature
    raw_body = await request.body()
    signature = request.headers.get("x-trello-webhook", "")
    callback_url = str(request.url)

    if not TrelloClient.verify_webhook_signature(
        api_secret=credential.api_token,
        body=raw_body,
        callback_url=callback_url,
        signature=signature,
    ):
        logger.warning(
            "trello_webhook_invalid_signature",
            webhook_id=webhook.id,
            trello_webhook_id=trello_webhook_id,
        )
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")

    # Parse and dispatch
    from app.schemas.trello import TrelloAPIWebhookPayload
    import json

    try:
        payload = TrelloAPIWebhookPayload.model_validate(json.loads(raw_body))
    except Exception as exc:
        logger.warning("trello_webhook_parse_error", error=str(exc))
        raise HTTPException(status_code=422, detail=f"Failed to parse payload: {exc}")

    ws_manager = _get_ws_manager(request)
    svc = TrelloWebhookService(session, ws_manager)
    await svc.handle_payload(webhook, payload)
    await session.commit()

    return {"ok": True}
