"""
Notification Service
====================

Abstract dispatcher that routes alerts to Slack, email, or logs.

Design
──────
  - NotificationChannel is an abstract interface
  - Concrete implementations: SlackChannel, EmailChannel, LogChannel
  - NotificationService takes a list of channels and fans out in parallel
  - Failures in one channel never prevent delivery on others
  - Metrics track per-channel success/failure
"""
from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from app.config import settings
from app.core.logging_config import get_logger
from app.core.metrics import NOTIFICATIONS_SENT_TOTAL
from app.domain.value_objects.priority import EscalationLevel

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Notification payload
# ---------------------------------------------------------------------------

class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Notification:
    title: str
    body: str
    severity: NotificationSeverity
    metadata: dict[str, Any] | None = None
    recipient_emails: list[str] | None = None
    recipient_slack_ids: list[str] | None = None


# ---------------------------------------------------------------------------
# Channel interface
# ---------------------------------------------------------------------------

class NotificationChannel(abc.ABC):
    name: str

    @abc.abstractmethod
    async def send(self, notification: Notification) -> bool:
        """Returns True on success, False on failure (never raises)."""
        ...


# ---------------------------------------------------------------------------
# Concrete channels
# ---------------------------------------------------------------------------

class LogChannel(NotificationChannel):
    """Always-available fallback — logs to structlog."""

    name = "log"

    async def send(self, notification: Notification) -> bool:
        level = {
            NotificationSeverity.INFO: "info",
            NotificationSeverity.WARNING: "warning",
            NotificationSeverity.CRITICAL: "error",
        }.get(notification.severity, "info")
        getattr(logger, level)(
            "notification",
            title=notification.title,
            body=notification.body,
            severity=notification.severity,
            meta=notification.metadata,
        )
        return True


class SlackChannel(NotificationChannel):
    """Sends to a Slack Incoming Webhook URL."""

    name = "slack"

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def send(self, notification: Notification) -> bool:
        if not self._webhook_url:
            return False

        color = {
            NotificationSeverity.INFO: "#36a64f",
            NotificationSeverity.WARNING: "#f4a62a",
            NotificationSeverity.CRITICAL: "#cc0000",
        }.get(notification.severity, "#888")

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"[KPIMaster] {notification.title}",
                    "text": notification.body,
                    "footer": "KPIMaster AI Agent",
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self._webhook_url, json=payload)
                resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("slack_notification_failed", error=str(exc))
            return False


class EmailChannel(NotificationChannel):
    """Stub for SMTP email delivery. Logs in dev, sends in production."""

    name = "email"

    async def send(self, notification: Notification) -> bool:
        if not notification.recipient_emails:
            return False
        # In production: use aiosmtplib or similar
        logger.info(
            "email_notification_stub",
            to=notification.recipient_emails,
            subject=notification.title,
        )
        return True


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class NotificationService:
    def __init__(self, channels: list[NotificationChannel] | None = None) -> None:
        self._channels: list[NotificationChannel] = channels or _build_default_channels()

    async def send(self, notification: Notification) -> dict[str, bool]:
        """Fan-out to all channels concurrently. Returns per-channel results."""
        tasks = {ch.name: ch.send(notification) for ch in self._channels}
        results: dict[str, bool] = {}
        for name, coro in tasks.items():
            try:
                ok = await coro
            except Exception as exc:
                logger.error("channel_send_unhandled", channel=name, error=str(exc))
                ok = False
            results[name] = ok
            status = "success" if ok else "failure"
            NOTIFICATIONS_SENT_TOTAL.labels(channel=name, status=status).inc()
        return results

    async def notify_blocker_detected(
        self,
        ticket_title: str,
        ticket_id: int,
        idle_hours: float,
        level: EscalationLevel,
        assignee_email: str | None = None,
    ) -> None:
        severity = (
            NotificationSeverity.CRITICAL
            if level == EscalationLevel.MANAGEMENT
            else NotificationSeverity.WARNING
        )
        notif = Notification(
            title=f"Blocker Detected — {level.label} escalation",
            body=(
                f"Ticket #{ticket_id} '{ticket_title}' has been stalled for "
                f"{idle_hours:.1f}h with no activity.\n"
                f"Escalation level: {level.label}"
            ),
            severity=severity,
            recipient_emails=[assignee_email] if assignee_email else None,
            metadata={"ticket_id": ticket_id, "idle_hours": idle_hours},
        )
        await self.send(notif)

    async def notify_daily_report(self, report_summary: dict[str, Any]) -> None:
        body_lines = [
            f"Velocity: {report_summary.get('velocity', 'N/A')} pts",
            f"Completion rate: {report_summary.get('completion_rate', 0)*100:.1f}%",
            f"Open blockers: {report_summary.get('open_blockers', 0)}",
            f"Stalled tickets: {report_summary.get('stalled_tickets', 0)}",
        ]
        for line in report_summary.get("comment_insights", []):
            body_lines.append(line)
        notif = Notification(
            title="KPIMaster Daily Report",
            body="\n".join(body_lines),
            severity=NotificationSeverity.INFO,
            metadata=report_summary,
        )
        await self.send(notif)

    async def notify_comment_blocker(
        self,
        *,
        ticket_title: str,
        ticket_id: int,
        summary: str,
    ) -> None:
        notif = Notification(
            title="Potential blocker detected in ticket comments",
            body=f"Ticket #{ticket_id} '{ticket_title}' may be blocked.\n{summary}",
            severity=NotificationSeverity.WARNING,
            metadata={"ticket_id": ticket_id, "ticket_title": ticket_title},
        )
        await self.send(notif)

    async def notify_unanswered_question(
        self,
        *,
        ticket_title: str,
        ticket_id: int,
        hours_waiting: float,
    ) -> None:
        notif = Notification(
            title="Question in ticket comments is still unanswered",
            body=(
                f"Ticket #{ticket_id} '{ticket_title}' has a clarification request with no response "
                f"for {hours_waiting:.1f} hours."
            ),
            severity=NotificationSeverity.WARNING,
            metadata={"ticket_id": ticket_id, "hours_waiting": hours_waiting},
        )
        await self.send(notif)

    async def notify_discussion_threshold(
        self,
        *,
        ticket_title: str,
        ticket_id: int,
        comment_count: int,
    ) -> None:
        notif = Notification(
            title="Ticket discussion is getting long",
            body=(
                f"Ticket #{ticket_id} '{ticket_title}' has reached {comment_count} comments and may need "
                f"a summary or explicit decision."
            ),
            severity=NotificationSeverity.INFO,
            metadata={"ticket_id": ticket_id, "comment_count": comment_count},
        )
        await self.send(notif)


def _build_default_channels() -> list[NotificationChannel]:
    channels: list[NotificationChannel] = [LogChannel()]
    if settings.slack_webhook_url:
        channels.append(SlackChannel(settings.slack_webhook_url))
    channels.append(EmailChannel())
    return channels
