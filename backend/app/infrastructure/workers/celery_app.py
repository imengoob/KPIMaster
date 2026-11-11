"""
Celery application factory.

Worker launch commands:
  # Worker
  celery -A app.infrastructure.workers.celery_app worker --loglevel=info -Q default,high_priority

  # Beat scheduler (periodic tasks)
  celery -A app.infrastructure.workers.celery_app beat --loglevel=info

  # Combined (dev only)
  celery -A app.infrastructure.workers.celery_app worker --beat --loglevel=info
"""
from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "sprintpulse",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.infrastructure.workers.tasks",
        "app.infrastructure.workers.integration_tasks",
    ],
)

# ── Serialisation ─────────────────────────────────────────────────────────────
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True

# ── Task routing ──────────────────────────────────────────────────────────────
celery_app.conf.task_routes = {
    "app.infrastructure.workers.tasks.generate_daily_report": {"queue": "high_priority"},
    "app.infrastructure.workers.tasks.scan_tickets": {"queue": "default"},
    "app.infrastructure.workers.tasks.detect_blockers": {"queue": "default"},
    "app.infrastructure.workers.tasks.compute_kpis": {"queue": "default"},
    "app.infrastructure.workers.tasks.refresh_burndown": {"queue": "default"},
    "app.infrastructure.workers.tasks.scan_repository_activity": {"queue": "default"},
    # Trello tasks
    "app.infrastructure.workers.tasks.trello_incremental_sync_all": {"queue": "default"},
    "app.infrastructure.workers.tasks.trello_compute_analytics_all": {"queue": "default"},
    "app.infrastructure.workers.tasks.trello_full_sync_board": {"queue": "default"},
    "app.infrastructure.workers.tasks.trello_comment_monitor": {"queue": "default"},
}

# ── Retry defaults ────────────────────────────────────────────────────────────
celery_app.conf.task_acks_late = True                 # Only ack after success
celery_app.conf.task_reject_on_worker_lost = True     # Requeue on crash
celery_app.conf.task_default_retry_delay = 60         # 1 minute between retries
celery_app.conf.task_max_retries = 3

# ── Beat schedule (periodic tasks) ───────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Daily report at 6:00 PM UTC
    "daily-report-6pm": {
        "task": "app.infrastructure.workers.tasks.generate_daily_report",
        "schedule": crontab(hour=18, minute=0),
        "options": {"queue": "high_priority"},
    },
    # Ticket quality scan every 5 minutes
    "ticket-scan-5min": {
        "task": "app.infrastructure.workers.tasks.scan_tickets",
        "schedule": settings.ticket_scan_interval_seconds,
        "options": {"queue": "default"},
    },
    # Blocker detection every 10 minutes
    "blocker-detection-10min": {
        "task": "app.infrastructure.workers.tasks.detect_blockers",
        "schedule": 600.0,
        "options": {"queue": "default"},
    },
    # KPI computation every 30 minutes for all active sprints
    "kpi-computation-30min": {
        "task": "app.infrastructure.workers.tasks.compute_kpis",
        "schedule": 1800.0,
        "options": {"queue": "default"},
    },
    # Burndown refresh every hour
    "burndown-refresh-1h": {
        "task": "app.infrastructure.workers.tasks.refresh_burndown",
        "schedule": 3600.0,
        "options": {"queue": "default"},
    },
    # Repository activity scan every 15 minutes
    "repo-scan-15min": {
        "task": "app.infrastructure.workers.tasks.scan_repository_activity",
        "schedule": 900.0,
        "options": {"queue": "default"},
    },
    # ── Trello ───────────────────────────────────────────────────────────────
    # Incremental sync every 5 minutes (polling fallback when webhooks miss events)
    "trello-incremental-sync-5min": {
        "task": "app.infrastructure.workers.tasks.trello_incremental_sync_all",
        "schedule": 300.0,
        "options": {"queue": "default"},
    },
    # Analytics + stall detection every 15 minutes
    "trello-analytics-15min": {
        "task": "app.infrastructure.workers.tasks.trello_compute_analytics_all",
        "schedule": 900.0,
        "options": {"queue": "default"},
    },
    "trello-comment-monitor-30min": {
        "task": "app.infrastructure.workers.tasks.trello_comment_monitor",
        "schedule": 1800.0,
        "options": {"queue": "default"},
    },
    # ── Multi-provider integrations ───────────────────────────────────────────
    # Incremental sync every 5 min (Jira, Microsoft, Trello via unified adapter)
    "integration-incremental-sync-5min": {
        "task": "integration_incremental_sync_all",
        "schedule": 300.0,
        "options": {"queue": "default"},
    },
    # Full re-sync every hour
    "integration-full-sync-1hour": {
        "task": "integration_full_sync_all",
        "schedule": 3600.0,
        "options": {"queue": "default"},
    },
    # Proactive token refresh every 45 minutes
    "integration-token-refresh-45min": {
        "task": "integration_refresh_expiring_tokens",
        "schedule": 2700.0,
        "options": {"queue": "high_priority"},
    },
}
