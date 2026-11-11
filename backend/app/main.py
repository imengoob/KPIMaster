"""
KPIMaster — Intelligent Support Agent for Ticket & Sprint Monitoring
FastAPI application entry point.

Startup sequence:
  1. Configure structured logging
  2. Connect to PostgreSQL (verify pool)
  3. Start event bus (Redis or in-memory)
  4. Register event handlers (WebSocket fan-out, notification triggers)
  5. Initialise WebSocket manager
  6. Mount API router + middleware

Shutdown sequence:
  1. Close WebSocket connections
  2. Stop event bus (drain pending messages)
  3. Dispose DB engine
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select

from app.api.v1.router import api_router
from app.config import settings
from app.core.http_basic_auth import (
    constant_time_credentials_match,
    parse_basic_auth_header,
)
from app.core.security import decode_access_token, hash_password, parse_bearer_token
from app.core.exceptions import KPIMasterError
from app.core.logging_config import configure_logging, get_logger
from app.core.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL, get_metrics_response
from app.database import check_database_health, engine, get_db_context
from app.infrastructure.websocket_manager import WebSocketManager
from app.models.user import User
# Pré-charge le modèle d'embeddings au démarrage plutôt qu'à la première requête
# force le chargement du modèles

configure_logging()
logger = get_logger(__name__)
_BASIC_AUTH_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/trello/webhooks/",
    # Only the OAuth *callbacks* are exempt — they receive browser redirects from
    # Atlassian/Microsoft without a Bearer token. The /start endpoints are called
    # by the frontend with a Bearer token and must go through auth middleware.
    "/api/v1/integrations/oauth/jira/callback",
    "/api/v1/integrations/oauth/microsoft/callback",
    "/api/v1/integrations/webhooks/",)
   
# Only login + register are exempt. /auth/me MUST go through the middleware
# so that request.state.auth_user_id is populated from the Bearer token.
_JWT_AUTH_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/trello/webhooks/",
    # Only the OAuth *callbacks* are exempt — they receive browser redirects from
    # Atlassian/Microsoft without a Bearer token. The /start endpoints are called
    # by the frontend with a Bearer token and must go through auth middleware.
    "/api/v1/integrations/oauth/jira/callback",
    "/api/v1/integrations/oauth/microsoft/callback",
    # Incoming webhooks from Jira/Microsoft are HMAC/client-state verified
    "/api/v1/integrations/webhooks/",

)


# ---------------------------------------------------------------------------
# Application lifespan (replaces deprecated on_event)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("sprintpulse_starting", env=settings.app_env, version=settings.app_version)

    if settings.app_env != "testing":
        # Verify database connectivity
        db_ok = await check_database_health()
        if not db_ok:
            logger.error("database_unreachable_on_startup")
            # Don't crash — allow readiness probe to report unhealthy
        else:
            logger.info("database_connected")
            await _ensure_bootstrap_user()

    # Initialise WebSocket manager (singleton on app.state)
    app.state.ws_manager = WebSocketManager()

    # Start event bus
    if settings.app_env == "production":
        from app.infrastructure.event_bus.redis_event_bus import RedisEventBus
        event_bus = RedisEventBus()
    else:
        from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus
        event_bus = InMemoryEventBus()

    await event_bus.start()
    app.state.event_bus = event_bus

    # Register event → WebSocket broadcast handler
    await _register_event_handlers(app)

    logger.info("sprintpulse_ready")

    yield  # ── Application running ──

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("sprintpulse_shutting_down")
    await event_bus.stop()
    await engine.dispose()
    logger.info("sprintpulse_stopped")


async def _register_event_handlers(app: FastAPI) -> None:
    """
    Wire domain events to real-time WebSocket broadcasts and notifications.
    This is the fan-out layer: event bus → WebSocket clients.
    """
    from app.domain.events.ticket_events import (
        BlockerDetectedEvent,
        BlockerEscalatedEvent,
        RepoActivityUpdatedEvent,
        TicketStalledEvent,
        TicketUpdatedEvent,
    )
    from app.services.notification_service import NotificationService

    bus = app.state.event_bus
    ws = app.state.ws_manager
    notif_svc = NotificationService()

    async def _broadcast_ticket_event(event):
        payload = {
            "type": event.event_type,
            "payload": event.model_dump(mode="json"),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        project_id = getattr(event, "project_id", None)
        if project_id:
            await ws.broadcast_to_project(project_id, payload)
        else:
            await ws.broadcast_global(payload)

    async def _handle_blocker_detected(event: BlockerDetectedEvent):
        await _broadcast_ticket_event(event)
        await notif_svc.notify_blocker_detected(
            ticket_title=f"Ticket #{event.ticket_id}",
            ticket_id=event.ticket_id,
            idle_hours=event.stall_hours,
            level=event.escalation_level,
        )

    # Subscribe handlers
    await bus.subscribe("ticket.*", _broadcast_ticket_event)
    await bus.subscribe("blocker.detected", _handle_blocker_detected)
    await bus.subscribe("blocker.escalated", _broadcast_ticket_event)
    await bus.subscribe("repo.activity.updated", _broadcast_ticket_event)
    await bus.subscribe("sprint.*", _broadcast_ticket_event)


async def _ensure_bootstrap_user() -> None:
    username = (settings.auth_bootstrap_username or "").strip()
    email = (settings.auth_bootstrap_email or "").strip().lower()
    password = settings.auth_bootstrap_password or ""
    if not username or not email or not password:
        return

    async with get_db_context() as session:
        existing = await session.scalar(
            select(User).where(or_(User.username == username, User.email == email))
        )
        if existing:
            return

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role="super_admin",
            is_active=True,
            is_superuser=True,
        )
        session.add(user)
        await session.flush()
        logger.info("bootstrap_user_created", username=username)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title="KPIMaster API",
        description="Intelligent AI Support Agent for Ticket & Sprint Monitoring",
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Auth uses Bearer tokens sent in the Authorization header — cookies are
    # never involved, so allow_credentials is NOT needed.
    # Browsers block allow_origins=["*"] when allow_credentials=True (CORS spec),
    # so we use the wildcard only (safe for token-based APIs).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "Accept", "*"],
    )

    # ── Observability middleware ───────────────────────────────────────────────
    @app.middleware("http")
    async def basic_auth_middleware(request: Request, call_next):
        if not settings.basic_auth_enabled:
            return await call_next(request)

        # CORS preflight — let CORSMiddleware handle it
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in _BASIC_AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        expected_username = settings.basic_auth_username or ""
        expected_password = settings.basic_auth_password or ""
        if not expected_username or not expected_password:
            logger.error(
                "basic_auth_enabled_without_credentials",
                path=path,
            )
            return JSONResponse(
                status_code=503,
                content={"detail": "Basic auth is enabled but credentials are not configured."},
            )

        parsed = parse_basic_auth_header(request.headers.get("authorization"))
        if parsed is None:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="KPIMaster Test Access"'},
            )

        username, password = parsed
        if not constant_time_credentials_match(
            username=username,
            password=password,
            expected_username=expected_username,
            expected_password=expected_password,
        ):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="KPIMaster Test Access"'},
            )

        return await call_next(request)

    @app.middleware("http")
    async def jwt_auth_middleware(request: Request, call_next):
        if not settings.auth_enabled:
            return await call_next(request)

        # CORS preflight — browsers send OPTIONS without auth headers
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/v1"):
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in _JWT_AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        token = parse_bearer_token(request.headers.get("authorization"))
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Missing bearer token."})

        payload = decode_access_token(token)
        if not payload or not payload.get("sub"):
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token."})

        request.state.auth_user_id = payload["sub"]
        return await call_next(request)

    # ── Observability middleware ───────────────────────────────────────────────
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start

        path = request.url.path
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            path=path,
            status_code=str(response.status_code),
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            path=path,
        ).observe(duration)
        return response

    # ── Global exception handler ───────────────────────────────────────────────
    @app.exception_handler(KPIMasterError)
    async def domain_error_handler(request: Request, exc: KPIMasterError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_global_exception", path=request.url.path, method=request.method, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
                "detail": "Our engineers have been notified.",
            },
        )

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # Health check
    @app.get("/health", tags=["Ops"])
    async def health():
        from app.database import check_database_health
        db_ok = await check_database_health()
        redis_ok = await _check_redis()
        return {
            "status": "healthy" if (db_ok and redis_ok) else "degraded",
            "version": settings.app_version,
            "database": db_ok,
            "redis": redis_ok,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # Prometheus metrics
    @app.get("/metrics", tags=["Ops"], include_in_schema=False)
    async def metrics():
        body, content_type = get_metrics_response()
        return Response(content=body, media_type=content_type)

    return app


async def _check_redis() -> bool:
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


app = create_app()
