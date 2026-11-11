"""
Burndown Chart Generator
========================

Generates or refreshes the burndown_entries table for a sprint.

Algorithm
─────────
  For each calendar day D in [sprint.start_date, today]:
    1.  Sum story_points for tickets where status == DONE and updated_at.date() <= D
    2.  remaining = committed_points - completed_on_or_before_D
    3.  ideal_remaining = linear interpolation from committed → 0 over sprint duration
    4.  Upsert BurndownEntry for (sprint_id, date=D)

The upsert is idempotent — safe to call repeatedly.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.domain.value_objects.ticket_status import TicketStatus
from app.models.burndown_entry import BurndownEntry
from app.models.sprint import Sprint
from app.models.ticket import Ticket
from app.repositories.sprint_repository import SprintRepository
from app.schemas.burndown import BurndownChart, BurndownEntryResponse

logger = get_logger(__name__)


class BurndownService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sprint_repo = SprintRepository(session)

    async def refresh_burndown(self, sprint_id: int) -> BurndownChart:
        """
        Recompute all burndown entries for a sprint up to today.
        Uses an upsert to avoid duplicates.
        """
        sprint = await self._sprint_repo.get_by_id(sprint_id)
        if not sprint:
            raise ValueError(f"Sprint {sprint_id} not found")

        tickets = await self._get_sprint_tickets(sprint_id)
        entries = self._compute_entries(sprint, tickets)

        # Bulk upsert via PostgreSQL ON CONFLICT DO UPDATE
        if entries:
            values = [
                {
                    "sprint_id": sprint_id,
                    "date": e.date,
                    "remaining_points": e.remaining_points,
                    "completed_points": e.completed_points,
                    "ideal_remaining": e.ideal_remaining,
                    "cumulative_completed": e.cumulative_completed,
                }
                for e in entries
            ]
            stmt = pg_insert(BurndownEntry).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["sprint_id", "date"],
                set_={
                    "remaining_points": stmt.excluded.remaining_points,
                    "completed_points": stmt.excluded.completed_points,
                    "ideal_remaining": stmt.excluded.ideal_remaining,
                    "cumulative_completed": stmt.excluded.cumulative_completed,
                },
            )
            await self._session.execute(stmt)

        logger.info("burndown_refreshed", sprint_id=sprint_id, days=len(entries))
        return await self.get_chart(sprint_id)

    async def get_chart(self, sprint_id: int) -> BurndownChart:
        sprint = await self._sprint_repo.get_by_id(sprint_id)
        if not sprint:
            raise ValueError(f"Sprint {sprint_id} not found")

        stmt = (
            select(BurndownEntry)
            .where(BurndownEntry.sprint_id == sprint_id)
            .order_by(BurndownEntry.date)
        )
        result = await self._session.execute(stmt)
        db_entries = list(result.scalars().all())

        return BurndownChart(
            sprint_id=sprint_id,
            sprint_name=sprint.name,
            start_date=sprint.start_date,
            end_date=sprint.end_date,
            committed_points=sprint.committed_points,
            entries=[BurndownEntryResponse.model_validate(e) for e in db_entries],
        )

    # ── Pure computation ────────────────────────────────────────────────────

    def _compute_entries(
        self, sprint: Sprint, tickets: list[Ticket]
    ) -> list[BurndownEntryResponse]:
        today = datetime.now(UTC).date()
        start = sprint.start_date
        end = min(sprint.end_date, today)
        committed = sprint.committed_points or 0
        sprint_days = max((sprint.end_date - start).days, 1)

        # Build a dict: date → cumulative completed story points
        done_by_date: dict[date, int] = {}
        for t in tickets:
            if t.status == TicketStatus.DONE.value and t.updated_at:
                completed_date = (
                    t.updated_at.date()
                    if isinstance(t.updated_at, datetime)
                    else t.updated_at
                )
                pts = t.story_points or 0
                if completed_date not in done_by_date:
                    done_by_date[completed_date] = 0
                done_by_date[completed_date] += pts

        entries: list[BurndownEntryResponse] = []
        cumulative = 0
        day = start

        while day <= end:
            daily_completed = done_by_date.get(day, 0)
            cumulative += daily_completed

            days_elapsed = (day - start).days
            ideal_remaining = max(
                committed * (1 - days_elapsed / sprint_days), 0.0
            )
            remaining = max(committed - cumulative, 0)

            entries.append(
                BurndownEntryResponse(
                    id=0,  # filled by DB on upsert
                    sprint_id=sprint.id,
                    date=day,
                    remaining_points=remaining,
                    completed_points=daily_completed,
                    ideal_remaining=round(ideal_remaining, 2),
                    cumulative_completed=cumulative,
                )
            )
            day += timedelta(days=1)

        return entries

    async def _get_sprint_tickets(self, sprint_id: int) -> list[Ticket]:
        stmt = select(Ticket).where(Ticket.sprint_id == sprint_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
