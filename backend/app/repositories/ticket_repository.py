"""
Ticket repository — all ticket-specific queries live here.

Never put SQL in services. Services call repositories.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.value_objects.ticket_status import TicketStatus
from app.models.ticket import Ticket
from app.repositories.base import BaseRepository


class TicketRepository(BaseRepository[Ticket]):
    model = Ticket

    async def get_with_relations(self, ticket_id: int) -> Ticket | None:
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.assignee),
                selectinload(Ticket.reporter),
                selectinload(Ticket.blockers),
                selectinload(Ticket.repository_activity),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_sprint(self, sprint_id: int) -> list[Ticket]:
        stmt = (
            select(Ticket)
            .where(Ticket.sprint_id == sprint_id)
            .options(selectinload(Ticket.assignee))
            .order_by(Ticket.priority.desc(), Ticket.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_project(
        self,
        project_id: int,
        *,
        status: TicketStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Ticket]:
        filters = [Ticket.project_id == project_id]
        if status:
            filters.append(Ticket.status == status.value)
        stmt = (
            select(Ticket)
            .where(and_(*filters))
            .offset(offset)
            .limit(limit)
            .order_by(Ticket.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_stalled_tickets(self, threshold_hours: int) -> list[Ticket]:
        """
        Returns tickets that have had no activity for more than
        `threshold_hours` and are in an active state (not terminal).
        """
        cutoff = datetime.now(UTC) - timedelta(hours=threshold_hours)
        active_statuses = [
            TicketStatus.IN_PROGRESS.value,
            TicketStatus.IN_REVIEW.value,
            TicketStatus.BLOCKED.value,
        ]
        stmt = (
            select(Ticket)
            .where(
                and_(
                    Ticket.status.in_(active_statuses),
                    Ticket.last_activity_at < cutoff,
                )
            )
            .options(
                selectinload(Ticket.assignee),
                selectinload(Ticket.blockers),
            )
            .order_by(Ticket.last_activity_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_tickets_without_commits(self) -> list[Ticket]:
        """In-progress tickets with zero repository activity."""
        from app.models.repository_activity import RepositoryActivity

        stmt = (
            select(Ticket)
            .outerjoin(
                RepositoryActivity,
                RepositoryActivity.ticket_id == Ticket.id,
            )
            .where(
                and_(
                    Ticket.status == TicketStatus.IN_PROGRESS.value,
                    or_(
                        RepositoryActivity.id.is_(None),
                        RepositoryActivity.commit_count == 0,
                    ),
                )
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_update_quality_scores(
        self, updates: dict[int, float]
    ) -> None:
        """Efficiently update quality scores for many tickets at once."""
        if not updates:
            return
        for ticket_id, score in updates.items():
            await self.session.execute(
                update(Ticket)
                .where(Ticket.id == ticket_id)
                .values(quality_score=score)
            )

    async def touch_activity(self, ticket_id: int) -> None:
        """Update last_activity_at to now — called on any field change."""
        await self.session.execute(
            update(Ticket)
            .where(Ticket.id == ticket_id)
            .values(last_activity_at=datetime.now(UTC))
        )

    async def get_completed_tickets_for_sprint(self, sprint_id: int) -> list[Ticket]:
        stmt = select(Ticket).where(
            and_(
                Ticket.sprint_id == sprint_id,
                Ticket.status == TicketStatus.DONE.value,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_in_progress_without_assignee(self) -> list[Ticket]:
        stmt = select(Ticket).where(
            and_(
                Ticket.status == TicketStatus.IN_PROGRESS.value,
                Ticket.assignee_id.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
