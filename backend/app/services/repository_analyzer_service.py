"""
Repository Activity Analyzer
=============================

Simulates Git/GitHub webhook ingestion and detects mismatches between
ticket status and observed repository activity.

Mismatch Types
──────────────
  no_commits_in_progress   — ticket is IN_PROGRESS but has zero commits
  pr_not_merged_done        — ticket is DONE but PR is not merged
  stale_branch              — last commit > 48h ago, ticket still IN_PROGRESS
  no_pr_in_review           — ticket is IN_REVIEW but no open PR found

In production, replace _simulate_git_activity() with a real GitHub/GitLab
API call using httpx with circuit-breaker protection.
"""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.core.metrics import REPO_MISMATCHES_TOTAL
from app.domain.events.ticket_events import RepoActivityUpdatedEvent
from app.domain.value_objects.ticket_status import TicketStatus
from app.models.repository_activity import RepositoryActivity
from app.models.ticket import Ticket
from app.repositories.ticket_repository import TicketRepository

logger = get_logger(__name__)

_STALE_COMMIT_HOURS = 48


def _parse_bound(value: str | None) -> datetime | None:
    if not value:
        return None
    from dateutil.parser import parse as parse_date

    parsed = parse_date(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class RepositoryAnalyzerService:
    def __init__(self, session: AsyncSession, event_bus=None) -> None:
        self._session = session
        self._event_bus = event_bus
        self._ticket_repo = TicketRepository(session)

    async def scan_project(self, project_id: int) -> dict[str, int]:
        """
        Scan all active tickets for a project and detect mismatches.
        Returns summary stats.
        """
        stmt = select(Ticket).where(
            and_(
                Ticket.project_id == project_id,
                Ticket.status.in_([
                    TicketStatus.IN_PROGRESS.value,
                    TicketStatus.IN_REVIEW.value,
                    TicketStatus.DONE.value,
                ]),
            )
        )
        result = await self._session.execute(stmt)
        tickets = list(result.scalars().all())

        mismatches = 0
        for ticket in tickets:
            activity = await self._get_or_create_activity(ticket)
            simulated = self._simulate_git_activity(ticket)

            # Update the activity record with simulated data
            activity.commit_count = simulated["commit_count"]
            activity.pr_count = simulated["pr_count"]
            activity.pr_merged = simulated["pr_merged"]
            activity.last_commit_at = simulated["last_commit_at"]
            activity.scanned_at = datetime.now(UTC)
            self._session.add(activity)

            # Mismatch detection
            mismatch, mtype, reason = self._detect_mismatch(ticket, activity)
            activity.mismatch_detected = mismatch
            activity.mismatch_type = mtype
            activity.mismatch_reason = reason

            if mismatch:
                mismatches += 1
                REPO_MISMATCHES_TOTAL.labels(mismatch_type=mtype or "unknown").inc()
                logger.warning(
                    "repo_mismatch_detected",
                    ticket_id=ticket.id,
                    mismatch_type=mtype,
                    reason=reason,
                )
                if self._event_bus:
                    event = RepoActivityUpdatedEvent(
                        ticket_id=ticket.id,
                        project_id=project_id,
                        commit_count=activity.commit_count,
                        pr_count=activity.pr_count,
                        mismatch_detected=True,
                        mismatch_reason=reason,
                    )
                    await self._event_bus.publish(event)

        await self._session.flush()
        logger.info(
            "repo_scan_complete",
            project_id=project_id,
            tickets_scanned=len(tickets),
            mismatches=mismatches,
        )
        return {"tickets_scanned": len(tickets), "mismatches": mismatches}

    async def get_mismatches(
        self,
        project_id: int,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> list[RepositoryActivity]:
        if provider is not None and provider != "github":
            return []

        stmt = select(RepositoryActivity).where(
            and_(
                RepositoryActivity.project_id == project_id,
                RepositoryActivity.mismatch_detected.is_(True),
            )
        )
        start_dt = _parse_bound(start_date)
        end_dt = _parse_bound(end_date)
        activity_anchor = func.coalesce(
            RepositoryActivity.last_commit_at,
            RepositoryActivity.scanned_at,
        )
        if start_dt is not None:
            stmt = stmt.where(activity_anchor >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(activity_anchor <= end_dt)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Internal ────────────────────────────────────────────────────────────

    async def _get_or_create_activity(self, ticket: Ticket) -> RepositoryActivity:
        stmt = select(RepositoryActivity).where(
            RepositoryActivity.ticket_id == ticket.id
        )
        result = await self._session.execute(stmt)
        activity = result.scalar_one_or_none()
        if activity is None:
            activity = RepositoryActivity(
                ticket_id=ticket.id,
                project_id=ticket.project_id,
                branch_name=f"feature/{ticket.id}-{ticket.title[:20].lower().replace(' ', '-')}",
            )
            self._session.add(activity)
            await self._session.flush()
            await self._session.refresh(activity)
        return activity

    @staticmethod
    def _simulate_git_activity(ticket: Ticket) -> dict:
        """
        Simulates GitHub activity for a ticket.
        In production, replace with a real API call.

        Intentionally introduces realistic variance — some tickets will
        have mismatches to exercise the detection logic.
        """
        rng = random.Random(ticket.id)  # deterministic per ticket for idempotency
        is_active = ticket.status in (
            TicketStatus.IN_PROGRESS.value,
            TicketStatus.IN_REVIEW.value,
        )

        if ticket.status == TicketStatus.DONE.value:
            commit_count = rng.randint(3, 20)
            pr_count = 1
            # 15% chance the PR isn't merged yet (simulates mismatch)
            pr_merged = rng.random() > 0.15
            last_commit_at = datetime.now(UTC) - timedelta(hours=rng.randint(1, 72))
        elif is_active:
            # 20% chance of zero commits (stall mismatch)
            commit_count = rng.randint(0, 15)
            pr_count = rng.randint(0, 2)
            pr_merged = False
            days_ago = rng.randint(0, 5)
            last_commit_at = datetime.now(UTC) - timedelta(days=days_ago)
        else:
            commit_count = 0
            pr_count = 0
            pr_merged = False
            last_commit_at = None

        return {
            "commit_count": commit_count,
            "pr_count": pr_count,
            "pr_merged": pr_merged,
            "last_commit_at": last_commit_at,
        }

    @staticmethod
    def _detect_mismatch(
        ticket: Ticket, activity: RepositoryActivity
    ) -> tuple[bool, str | None, str | None]:
        """Returns (mismatch_detected, mismatch_type, reason)."""
        status = ticket.status

        if (
            status == TicketStatus.IN_PROGRESS.value
            and activity.commit_count == 0
        ):
            return (
                True,
                "no_commits_in_progress",
                "Ticket is in-progress but has no commits associated with it.",
            )

        if (
            status == TicketStatus.DONE.value
            and activity.pr_count > 0
            and not activity.pr_merged
        ):
            return (
                True,
                "pr_not_merged_done",
                "Ticket is marked done but the pull request has not been merged.",
            )

        if (
            status == TicketStatus.IN_PROGRESS.value
            and activity.last_commit_at is not None
        ):
            last = activity.last_commit_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            idle_hours = (datetime.now(UTC) - last).total_seconds() / 3600
            if idle_hours > _STALE_COMMIT_HOURS:
                return (
                    True,
                    "stale_branch",
                    f"Last commit was {idle_hours:.0f}h ago while ticket remains in-progress.",
                )

        if (
            status == TicketStatus.IN_REVIEW.value
            and activity.pr_count == 0
        ):
            return (
                True,
                "no_pr_in_review",
                "Ticket is in review but no pull request was found.",
            )

        return False, None, None
