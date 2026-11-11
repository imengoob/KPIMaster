"""
Ticket Monitoring Engine
========================

Periodically scans every ticket in active sprints and:
  1. Computes a quality score (0–100)
  2. Records which quality gates failed
  3. Updates the quality_score column
  4. Publishes TicketUpdatedEvent for downstream consumers

Quality Gates
─────────────
  +20 pts  — has description (non-empty)
  +20 pts  — has an assignee
  +20 pts  — has a non-default priority (not MEDIUM when in-progress)
  +20 pts  — has estimation (estimated_hours or story_points)
  +20 pts  — title is descriptive (>= 10 chars, not generic)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.core.metrics import TICKETS_SCANNED_TOTAL
from app.domain.events.ticket_events import TicketUpdatedEvent
from app.domain.value_objects.ticket_status import TicketStatus
from app.models.ticket import Ticket
from app.repositories.ticket_repository import TicketRepository
from app.schemas.ticket import TicketQualityReport

logger = get_logger(__name__)

_GENERIC_TITLES = frozenset({
    "fix bug", "task", "new feature", "update", "misc", "todo",
    "wip", "work in progress", "tbd",
})


@dataclass
class _QualityCheck:
    name: str
    points: int
    passed: bool
    recommendation: str = ""


class TicketMonitoringService:
    """
    Stateless service — instantiated per request or per worker execution.
    Inject an AsyncSession; all writes go through the TicketRepository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TicketRepository(session)

    # ── Public API ──────────────────────────────────────────────────────────

    async def scan_all_active_tickets(self) -> list[TicketQualityReport]:
        """
        Full sweep: fetch all active-sprint tickets, score them, persist.
        Called by the background worker every N minutes.
        """
        from app.repositories.sprint_repository import SprintRepository

        sprint_repo = SprintRepository(self._session)
        active_sprints = await sprint_repo.get_all_active_sprints()

        reports: list[TicketQualityReport] = []
        score_updates: dict[int, float] = {}

        for sprint in active_sprints:
            tickets = await self._repo.get_by_sprint(sprint.id)
            for ticket in tickets:
                report = self.evaluate_ticket_quality(ticket)
                reports.append(report)
                score_updates[ticket.id] = report.quality_score
                TICKETS_SCANNED_TOTAL.inc()

        await self._repo.bulk_update_quality_scores(score_updates)
        logger.info("ticket_scan_complete", tickets_scanned=len(reports))
        return reports

    def evaluate_ticket_quality(self, ticket: Ticket) -> TicketQualityReport:
        """
        Synchronous quality evaluation — no I/O, suitable for unit testing.
        Returns a TicketQualityReport with score + actionable recommendations.
        """
        checks: list[_QualityCheck] = [
            self._check_description(ticket),
            self._check_assignee(ticket),
            self._check_priority(ticket),
            self._check_estimation(ticket),
            self._check_title(ticket),
        ]

        total_score = sum(c.points for c in checks if c.passed)
        issues = [c.name for c in checks if not c.passed]
        recs = [c.recommendation for c in checks if not c.passed and c.recommendation]

        return TicketQualityReport(
            ticket_id=ticket.id,
            quality_score=float(total_score),
            issues=issues,
            has_description=next(c.passed for c in checks if "description" in c.name.lower()),
            has_assignee=next(c.passed for c in checks if "assignee" in c.name.lower()),
            has_priority=next(c.passed for c in checks if "priority" in c.name.lower()),
            has_estimation=next(c.passed for c in checks if "estimation" in c.name.lower()),
            recommendations=recs,
        )

    # ── Private quality gate evaluators ────────────────────────────────────

    @staticmethod
    def _check_description(ticket: Ticket) -> _QualityCheck:
        has = bool(ticket.description and len(ticket.description.strip()) >= 20)
        return _QualityCheck(
            name="missing_description",
            points=20,
            passed=has,
            recommendation=(
                "Add a description with acceptance criteria (min 20 chars)."
                if not has
                else ""
            ),
        )

    @staticmethod
    def _check_assignee(ticket: Ticket) -> _QualityCheck:
        skip = ticket.status in (TicketStatus.BACKLOG.value, TicketStatus.TODO.value)
        has = ticket.assignee_id is not None or skip
        return _QualityCheck(
            name="missing_assignee",
            points=20,
            passed=has,
            recommendation=(
                "Assign a developer before moving to In-Progress." if not has else ""
            ),
        )

    @staticmethod
    def _check_priority(ticket: Ticket) -> _QualityCheck:
        # Priority is always set (default = medium), so only penalise if
        # ticket is actively worked and still at default medium with no override.
        is_active = ticket.status in (
            TicketStatus.IN_PROGRESS.value,
            TicketStatus.IN_REVIEW.value,
        )
        if is_active and ticket.priority == "medium":
            # Treat as not explicitly set
            return _QualityCheck(
                name="default_priority_in_active_ticket",
                points=20,
                passed=False,
                recommendation="Confirm the ticket priority is intentionally Medium, or set it explicitly.",
            )
        return _QualityCheck(name="priority_set", points=20, passed=True)

    @staticmethod
    def _check_estimation(ticket: Ticket) -> _QualityCheck:
        has = ticket.estimated_hours is not None or ticket.story_points is not None
        return _QualityCheck(
            name="missing_estimation",
            points=20,
            passed=has,
            recommendation="Provide a story-point or hour estimate for planning accuracy." if not has else "",
        )

    @staticmethod
    def _check_title(ticket: Ticket) -> _QualityCheck:
        title = (ticket.title or "").strip()
        is_generic = title.lower() in _GENERIC_TITLES
        is_short = len(title) < 10
        passed = not is_generic and not is_short
        return _QualityCheck(
            name="poor_title",
            points=20,
            passed=passed,
            recommendation=(
                "Use a descriptive title (e.g. 'Fix null pointer in PaymentService.charge()')."
                if not passed
                else ""
            ),
        )
