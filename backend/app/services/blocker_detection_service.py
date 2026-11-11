"""
Blocker Detection Engine
========================

Implements a three-level escalation state machine.

Detection Flow
──────────────
  1. Fetch all tickets with status in {IN_PROGRESS, IN_REVIEW, BLOCKED}
  2. For each ticket, compute idle_hours = now - last_activity_at
  3. Compare against configured thresholds:
       idle >= L1_THRESHOLD  →  create Blocker or ensure level >= 1
       idle >= L2_THRESHOLD  →  escalate to level 2 (team lead)
       idle >= L3_THRESHOLD  →  escalate to level 3 (management)
  4. Publish BlockerDetectedEvent / BlockerEscalatedEvent
  5. Trigger notifications via NotificationService

Idempotency
───────────
  A Blocker record is unique per (ticket_id, resolved=None).
  Re-running the engine on the same ticket is safe — it only moves forward.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging_config import get_logger
from app.core.metrics import BLOCKER_DETECTIONS_TOTAL, OPEN_BLOCKERS_GAUGE
from app.domain.events.ticket_events import BlockerDetectedEvent, BlockerEscalatedEvent
from app.domain.value_objects.priority import EscalationLevel
from app.models.blocker import Blocker
from app.models.ticket import Ticket
from app.repositories.blocker_repository import BlockerRepository
from app.repositories.ticket_repository import TicketRepository

logger = get_logger(__name__)


class BlockerDetectionService:
    def __init__(
        self,
        session: AsyncSession,
        event_bus=None,  # injected; avoids circular import at construction
    ) -> None:
        self._session = session
        self._event_bus = event_bus
        self._ticket_repo = TicketRepository(session)
        self._blocker_repo = BlockerRepository(session)

    # ── Thresholds (pulled from config for runtime adjustability) ──────────
    @property
    def _l1_threshold(self) -> int:
        return settings.stall_threshold_l1_hours

    @property
    def _l2_threshold(self) -> int:
        return settings.stall_threshold_l2_hours

    @property
    def _l3_threshold(self) -> int:
        return settings.stall_threshold_l3_hours

    # ── Public API ──────────────────────────────────────────────────────────

    async def run_detection_sweep(self) -> dict[str, int]:
        """
        Full detection sweep across all stalled tickets.
        Returns summary stats: {new_blockers, escalated, resolved_auto}.
        """
        # Use the lowest threshold to fetch all potentially stalled tickets
        stalled = await self._ticket_repo.get_stalled_tickets(self._l1_threshold)

        stats = {"new_blockers": 0, "escalated": 0}

        for ticket in stalled:
            idle_hours = self._compute_idle_hours(ticket)
            result = await self._process_ticket(ticket, idle_hours)
            if result == "new":
                stats["new_blockers"] += 1
            elif result == "escalated":
                stats["escalated"] += 1

        # Update Prometheus gauge
        open_count = await self._blocker_repo.count(
            filters=[Blocker.resolved_at.is_(None)]
        )
        for level in (1, 2, 3):
            OPEN_BLOCKERS_GAUGE.labels(escalation_level=str(level)).set(0)
        for level in (1, 2, 3):
            level_count = await self._blocker_repo.count(
                filters=[
                    Blocker.resolved_at.is_(None),
                    Blocker.escalation_level == level,
                ]
            )
            OPEN_BLOCKERS_GAUGE.labels(escalation_level=str(level)).set(level_count)

        logger.info(
            "blocker_sweep_complete",
            stalled_tickets=len(stalled),
            **stats,
        )
        return stats

    async def resolve_blocker(self, blocker_id: int) -> Blocker | None:
        """Called when a ticket moves to DONE or is manually un-blocked."""
        blocker = await self._blocker_repo.get_by_id(blocker_id)
        if blocker and not blocker.is_resolved:
            blocker = await self._blocker_repo.update(
                blocker, resolved_at=datetime.now(UTC)
            )
            logger.info("blocker_resolved", blocker_id=blocker_id, ticket_id=blocker.ticket_id)
        return blocker

    # ── Internal ────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_idle_hours(ticket: Ticket) -> float:
        now = datetime.now(UTC)
        last = ticket.last_activity_at
        # Make last timezone-aware if naive
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return (now - last).total_seconds() / 3600

    async def _process_ticket(
        self, ticket: Ticket, idle_hours: float
    ) -> str:
        """
        State machine for one ticket.
        Returns: "new" | "escalated" | "unchanged"
        """
        if idle_hours < self._l1_threshold:
            return "unchanged"

        target_level = self._compute_target_level(idle_hours)
        existing = await self._blocker_repo.get_active_blocker_for_ticket(ticket.id)

        if existing is None:
            # Create new blocker at appropriate level
            blocker = Blocker(
                ticket_id=ticket.id,
                stall_hours=idle_hours,
                escalation_level=target_level.value,
                detected_at=datetime.now(UTC),
                description=(
                    f"Ticket stalled for {idle_hours:.1f}h — "
                    f"no activity since {ticket.last_activity_at.isoformat()}"
                ),
            )
            await self._blocker_repo.create(blocker)
            BLOCKER_DETECTIONS_TOTAL.labels(escalation_level=str(target_level.value)).inc()

            if self._event_bus:
                event = BlockerDetectedEvent(
                    blocker_id=blocker.id,
                    ticket_id=ticket.id,
                    project_id=ticket.project_id,
                    sprint_id=ticket.sprint_id,
                    escalation_level=target_level,
                    stall_hours=idle_hours,
                    assignee_id=ticket.assignee_id,
                )
                await self._event_bus.publish(event)

            logger.warning(
                "blocker_detected",
                ticket_id=ticket.id,
                idle_hours=round(idle_hours, 1),
                level=target_level.value,
            )
            return "new"

        # Existing blocker — check if we need to escalate
        if existing.escalation_level < target_level.value:
            prev_level = EscalationLevel(existing.escalation_level)
            await self._blocker_repo.update(
                existing,
                escalation_level=target_level.value,
                stall_hours=idle_hours,
                last_escalated_at=datetime.now(UTC),
            )

            if self._event_bus:
                event = BlockerEscalatedEvent(
                    blocker_id=existing.id,
                    ticket_id=ticket.id,
                    previous_level=prev_level,
                    new_level=target_level,
                )
                await self._event_bus.publish(event)

            logger.warning(
                "blocker_escalated",
                ticket_id=ticket.id,
                from_level=prev_level.value,
                to_level=target_level.value,
            )
            return "escalated"

        return "unchanged"

    def _compute_target_level(self, idle_hours: float) -> EscalationLevel:
        if idle_hours >= self._l3_threshold:
            return EscalationLevel.MANAGEMENT
        if idle_hours >= self._l2_threshold:
            return EscalationLevel.TEAM_LEAD
        return EscalationLevel.DEVELOPER
