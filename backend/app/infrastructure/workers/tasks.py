"""
Celery task definitions.

All tasks are idempotent — safe to retry or run multiple times.

Since Celery workers are synchronous Python processes (not async),
we use asyncio.run() to execute async service code.

For production at scale: consider celery-pool-asyncio or running
each task in a dedicated async context.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from celery import Task

from app.core.logging_config import get_logger
from app.infrastructure.workers.celery_app import celery_app

logger = get_logger(__name__)


async def _run_and_dispose(coro):
    try:
        return await coro
    finally:
        from app.database import engine

        await engine.dispose()


def _run(coro):
    """Execute a coroutine from synchronous Celery task context."""
    return asyncio.run(_run_and_dispose(coro))


# ── Task base class with structured error handling ────────────────────────────

class BaseTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "task_failed",
            task=self.name,
            task_id=task_id,
            error=str(exc),
            traceback=str(einfo),
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(
            "task_retrying",
            task=self.name,
            task_id=task_id,
            error=str(exc),
        )


# ── Tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.scan_tickets",
    max_retries=3,
)
def scan_tickets(self) -> dict[str, Any]:
    """
    Scan all tickets in active sprints and compute quality scores.
    Idempotent: running multiple times only updates scores, never creates duplicates.
    """
    async def _scan():
        from app.database import get_db_context
        from app.services.ticket_monitoring_service import TicketMonitoringService

        async with get_db_context() as session:
            svc = TicketMonitoringService(session)
            reports = await svc.scan_all_active_tickets()
            return {"tickets_scanned": len(reports)}

    try:
        result = _run(_scan())
        logger.info("scan_tickets_done", **result)
        return result
    except Exception as exc:
        logger.error("scan_tickets_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.detect_blockers",
    max_retries=3,
)
def detect_blockers(self) -> dict[str, Any]:
    """Run the blocker detection sweep across all stalled tickets."""

    async def _detect():
        from app.database import get_db_context
        from app.infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus
        from app.services.blocker_detection_service import BlockerDetectionService

        # Use in-memory bus in worker context; for production use RedisEventBus
        event_bus = InMemoryEventBus()
        await event_bus.start()

        async with get_db_context() as session:
            svc = BlockerDetectionService(session, event_bus=event_bus)
            stats = await svc.run_detection_sweep()

        await event_bus.stop()
        return stats

    try:
        result = _run(_detect())
        logger.info("detect_blockers_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.compute_kpis",
    max_retries=3,
)
def compute_kpis(self) -> dict[str, Any]:
    """Compute KPI snapshots for all active sprints."""

    async def _compute():
        from app.database import get_db_context
        from app.repositories.sprint_repository import SprintRepository
        from app.services.kpi_service import KPIService

        snapshots_created = 0
        async with get_db_context() as session:
            sprint_repo = SprintRepository(session)
            active_sprints = await sprint_repo.get_all_active_sprints()
            kpi_svc = KPIService(session)
            for sprint in active_sprints:
                await kpi_svc.compute_and_persist(sprint.project_id, sprint.id)
                snapshots_created += 1
        return {"snapshots_created": snapshots_created}

    try:
        result = _run(_compute())
        logger.info("compute_kpis_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.refresh_burndown",
    max_retries=3,
)
def refresh_burndown(self) -> dict[str, Any]:
    """Refresh burndown entries for all active sprints."""

    async def _refresh():
        from app.database import get_db_context
        from app.repositories.sprint_repository import SprintRepository
        from app.services.burndown_service import BurndownService

        refreshed = 0
        async with get_db_context() as session:
            sprint_repo = SprintRepository(session)
            active_sprints = await sprint_repo.get_all_active_sprints()
            burndown_svc = BurndownService(session)
            for sprint in active_sprints:
                await burndown_svc.refresh_burndown(sprint.id)
                refreshed += 1
        return {"sprints_refreshed": refreshed}

    try:
        result = _run(_refresh())
        logger.info("refresh_burndown_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.scan_repository_activity",
    max_retries=3,
)
def scan_repository_activity(self) -> dict[str, Any]:
    """Run the repository mismatch analysis for all active projects."""

    async def _scan():
        from app.database import get_db_context
        from app.repositories.project_repository import ProjectRepository
        from app.services.repository_analyzer_service import RepositoryAnalyzerService

        total_mismatches = 0
        async with get_db_context() as session:
            proj_repo = ProjectRepository(session)
            projects = await proj_repo.get_all_active()
            analyzer = RepositoryAnalyzerService(session)
            for project in projects:
                result = await analyzer.scan_project(project.id)
                total_mismatches += result["mismatches"]
        return {"total_mismatches": total_mismatches}

    try:
        result = _run(_scan())
        logger.info("repo_scan_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


# ── Trello tasks ──────────────────────────────────────────────────────────────

@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.trello_incremental_sync_all",
    max_retries=3,
)
def trello_incremental_sync_all(self) -> dict[str, Any]:
    """
    Incremental-sync every active Trello board.

    Runs every 5 minutes as a polling fallback for boards that may have
    missed a webhook (or whose webhook has not yet been registered).
    Falls back to full sync if `last_action_id` is NULL.
    """

    async def _sync():
        from app.database import get_db_context
        from app.models.trello_board import TrelloBoard
        from app.models.trello_credential import TrelloCredential
        from app.services.trello.sync_service import TrelloSyncService
        from sqlalchemy import select

        boards_synced = 0
        errors = 0

        async with get_db_context() as session:
            result = await session.execute(
                select(TrelloBoard)
                .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
                .where(TrelloCredential.is_active.is_(True), TrelloBoard.is_closed.is_(False))
            )
            boards = result.scalars().all()
            svc = TrelloSyncService(session)

            for board in boards:
                credential = await session.get(TrelloCredential, board.credential_id)
                if not credential:
                    continue
                try:
                    if board.last_action_id:
                        await svc.incremental_sync(board, credential)
                    else:
                        await svc.full_sync(board, credential)
                    boards_synced += 1
                except Exception as exc:
                    logger.warning(
                        "trello_sync_board_failed",
                        board_id=board.id,
                        error=str(exc),
                    )
                    errors += 1

        return {"boards_synced": boards_synced, "errors": errors}

    try:
        result = _run(_sync())
        logger.info("trello_incremental_sync_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.trello_compute_analytics_all",
    max_retries=3,
)
def trello_compute_analytics_all(self) -> dict[str, Any]:
    """
    Recompute analytics and run stall detection for every active Trello board.

    Emits TrelloCardStalledEvent for newly stalled cards and broadcasts
    TrelloAnalyticsUpdatedEvent over WebSocket to connected dashboards.

    Runs every 15 minutes.
    """

    async def _compute():
        from app.database import get_db_context
        from app.infrastructure.websocket_manager import WebSocketManager
        from app.models.trello_board import TrelloBoard
        from app.models.trello_credential import TrelloCredential
        from app.services.trello.analytics_service import TrelloAnalyticsService
        from sqlalchemy import select

        # Workers don't share the app's WS manager singleton; create a no-op
        # one that silently drops broadcasts (WebSocket push is best-effort).
        ws_manager = WebSocketManager()

        boards_processed = 0
        stalled_total = 0

        async with get_db_context() as session:
            result = await session.execute(
                select(TrelloBoard)
                .join(TrelloCredential, TrelloBoard.credential_id == TrelloCredential.id)
                .where(TrelloCredential.is_active.is_(True), TrelloBoard.is_closed.is_(False))
            )
            boards = result.scalars().all()
            svc = TrelloAnalyticsService(session, ws_manager)

            for board in boards:
                try:
                    analytics = await svc.compute_board_analytics(board)
                    stalled_total += analytics.stalled_count
                    boards_processed += 1
                except Exception as exc:
                    logger.warning(
                        "trello_analytics_board_failed",
                        board_id=board.id,
                        error=str(exc),
                    )

        return {"boards_processed": boards_processed, "stalled_cards": stalled_total}

    try:
        result = _run(_compute())
        logger.info("trello_analytics_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.trello_full_sync_board",
    max_retries=2,
)
def trello_full_sync_board(self, board_id: int) -> dict[str, Any]:
    """
    On-demand full sync for a single board.  Called after initial
    credential connection or from the API endpoint with ?full=true.
    """

    async def _sync():
        from app.database import get_db_context
        from app.models.trello_board import TrelloBoard
        from app.models.trello_credential import TrelloCredential
        from app.services.trello.sync_service import TrelloSyncService

        async with get_db_context() as session:
            board = await session.get(TrelloBoard, board_id)
            if not board:
                return {"error": f"Board {board_id} not found"}
            credential = await session.get(TrelloCredential, board.credential_id)
            if not credential:
                return {"error": "No credential"}

            svc = TrelloSyncService(session)
            event = await svc.full_sync(board, credential)

        return {
            "board_id": board_id,
            "cards_upserted": event.cards_upserted,
            "actions_processed": event.actions_processed,
            "duration_ms": round(event.sync_duration_ms),
        }

    try:
        result = _run(_sync())
        logger.info("trello_full_sync_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.generate_daily_report",
    max_retries=2,
)
def generate_daily_report(self) -> dict[str, Any]:
    """
    Daily report job — runs at 6 PM UTC.
    Computes KPIs, blockers, and sends notifications.
    """

    async def _report():
        from app.database import get_db_context
        from app.repositories.project_repository import ProjectRepository
        from app.repositories.sprint_repository import SprintRepository
        from app.services.kpi_service import KPIService
        from app.services.notification_service import NotificationService
        from app.services.trello.comment_analysis_service import TrelloCommentAnalysisService

        notif_svc = NotificationService()
        report_sent = 0

        async with get_db_context() as session:
            proj_repo = ProjectRepository(session)
            sprint_repo = SprintRepository(session)
            kpi_svc = KPIService(session)

            projects = await proj_repo.get_all_active()
            for project in projects:
                active_sprint = await sprint_repo.get_active_sprint(project.id)
                if not active_sprint:
                    continue

                snapshot = await kpi_svc.compute_and_persist(project.id, active_sprint.id)
                dashboard = await kpi_svc.get_dashboard(project.id, active_sprint.id)

                summary = {
                    "project": project.name,
                    "sprint": active_sprint.name,
                    "velocity": snapshot.velocity,
                    "completion_rate": snapshot.completion_rate,
                    "open_blockers": dashboard.open_blockers,
                    "stalled_tickets": dashboard.stalled_tickets,
                    "generated_at": datetime.now(UTC).isoformat(),
                }
                try:
                    comment_metrics = await TrelloCommentAnalysisService(session).analyze_project(project.id)
                    summary["comment_insights"] = comment_metrics.comment_insights_summary
                except Exception:
                    summary["comment_insights"] = []
                await notif_svc.notify_daily_report(summary)
                report_sent += 1

        return {"reports_sent": report_sent}

    try:
        result = _run(_report())
        logger.info("daily_report_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.infrastructure.workers.tasks.trello_comment_monitor",
    max_retries=2,
)
def trello_comment_monitor(self) -> dict[str, Any]:
    """
    Periodically analyze Trello comment threads and emit notification signals
    for blockers, unanswered questions, and heavy discussions.
    """

    async def _monitor():
        from app.core.metrics import COMMENT_INSIGHTS_TOTAL
        from app.database import get_db_context
        from app.config import settings
        from app.repositories.project_repository import ProjectRepository
        from app.services.notification_service import NotificationService
        from app.services.trello.comment_analysis_service import TrelloCommentAnalysisService
        import redis.asyncio as aioredis

        notif_svc = NotificationService()
        alerts_sent = 0
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

        async with get_db_context() as session:
            projects = await ProjectRepository(session).get_all_active()
            for project in projects:
                try:
                    metrics = await TrelloCommentAnalysisService(session).analyze_project(project.id)
                except Exception:
                    continue

                for ticket in metrics.tickets:
                    if ticket.potentially_blocked:
                        dedupe_key = f"trello:comment-alert:blocker:{ticket.ticket_id}"
                        if await redis_client.set(dedupe_key, "1", ex=43200, nx=True):
                            COMMENT_INSIGHTS_TOTAL.labels(kind="blocker_ticket").inc()
                            await notif_svc.notify_comment_blocker(
                                ticket_title=ticket.ticket_title,
                                ticket_id=ticket.ticket_id,
                                summary=ticket.ai_summary,
                            )
                            alerts_sent += 1

                    unanswered_questions = [
                        comment for comment in ticket.comments
                        if comment.classification == "Question / Clarification"
                        and comment.unanswered_for_hours is not None
                        and comment.unanswered_for_hours >= 24
                    ]
                    if unanswered_questions:
                        dedupe_key = f"trello:comment-alert:question:{ticket.ticket_id}"
                        if await redis_client.set(dedupe_key, "1", ex=43200, nx=True):
                            COMMENT_INSIGHTS_TOTAL.labels(kind="unanswered_question").inc()
                            await notif_svc.notify_unanswered_question(
                                ticket_title=ticket.ticket_title,
                                ticket_id=ticket.ticket_id,
                                hours_waiting=max(comment.unanswered_for_hours or 0 for comment in unanswered_questions),
                            )
                            alerts_sent += 1

                    if ticket.comment_count > 10:
                        dedupe_key = f"trello:comment-alert:discussion:{ticket.ticket_id}"
                        if await redis_client.set(dedupe_key, "1", ex=43200, nx=True):
                            COMMENT_INSIGHTS_TOTAL.labels(kind="long_discussion").inc()
                            await notif_svc.notify_discussion_threshold(
                                ticket_title=ticket.ticket_title,
                                ticket_id=ticket.ticket_id,
                                comment_count=ticket.comment_count,
                            )
                            alerts_sent += 1

        await redis_client.aclose()

        return {"alerts_sent": alerts_sent}

    try:
        result = _run(_monitor())
        logger.info("trello_comment_monitor_done", **result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)
