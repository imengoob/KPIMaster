"""
FastAPI dependency injection bindings.

All services and repositories are request-scoped unless otherwise noted.
The WebSocketManager and EventBus are application-scoped singletons.
"""
from __future__ import annotations
from fastapi import HTTPException, Request

from app.models.user import User

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

# ── Database session ──────────────────────────────────────────────────────────
DbSession = Annotated[AsyncSession, Depends(get_db)]

# ── Repositories ──────────────────────────────────────────────────────────────
def get_project_repo(session: DbSession):
    from app.repositories.project_repository import ProjectRepository
    return ProjectRepository(session)

def get_sprint_repo(session: DbSession):
    from app.repositories.sprint_repository import SprintRepository
    return SprintRepository(session)

def get_ticket_repo(session: DbSession):
    from app.repositories.ticket_repository import TicketRepository
    return TicketRepository(session)

def get_blocker_repo(session: DbSession):
    from app.repositories.blocker_repository import BlockerRepository
    return BlockerRepository(session)

# ── Services ──────────────────────────────────────────────────────────────────
def get_ticket_monitoring_svc(session: DbSession):
    from app.services.ticket_monitoring_service import TicketMonitoringService
    return TicketMonitoringService(session)

def get_blocker_detection_svc(session: DbSession):
    from app.services.blocker_detection_service import BlockerDetectionService
    from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus
    # In production, inject the shared RedisEventBus from app state
    return BlockerDetectionService(session)

def get_kpi_svc(session: DbSession):
    from app.services.kpi_service import KPIService
    return KPIService(session)

def get_burndown_svc(session: DbSession):
    from app.services.burndown_service import BurndownService
    return BurndownService(session)

def get_repo_analyzer_svc(session: DbSession):
    from app.services.repository_analyzer_service import RepositoryAnalyzerService
    return RepositoryAnalyzerService(session)
# ── Current authenticated user ────────────────────────────────────────────────
# Mirrors the logic already used in app/api/v1/auth.py's /auth/me endpoint:
# the JWT middleware (see app/main.py, jwt_auth_middleware) sets
# request.state.auth_user_id on every authenticated request; this dependency
# just resolves that into a full User row for routes that need it (like the
# new /assistant endpoints).




async def get_current_user(request: Request, session: DbSession) -> User:
    user_id = getattr(request.state, "auth_user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    user = await session.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid user.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

# ── Annotated shortcuts ───────────────────────────────────────────────────────
ProjectRepo = Annotated[object, Depends(get_project_repo)]
SprintRepo  = Annotated[object, Depends(get_sprint_repo)]
TicketRepo  = Annotated[object, Depends(get_ticket_repo)]
BlockerRepo = Annotated[object, Depends(get_blocker_repo)]

TicketMonitoringSvc = Annotated[object, Depends(get_ticket_monitoring_svc)]
BlockerDetectionSvc = Annotated[object, Depends(get_blocker_detection_svc)]
KPISvc              = Annotated[object, Depends(get_kpi_svc)]
BurndownSvc         = Annotated[object, Depends(get_burndown_svc)]
RepoAnalyzerSvc     = Annotated[object, Depends(get_repo_analyzer_svc)]
