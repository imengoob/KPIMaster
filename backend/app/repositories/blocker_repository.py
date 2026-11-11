from sqlalchemy import Integer, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.blocker import Blocker
from app.repositories.base import BaseRepository


class BlockerRepository(BaseRepository[Blocker]):
    model = Blocker

    async def get_open_blockers(self, project_id: int | None = None) -> list[Blocker]:
        stmt = (
            select(Blocker)
            .where(Blocker.resolved_at.is_(None))
            .options(selectinload(Blocker.ticket))
        )
        if project_id is not None:
            stmt = stmt.join(Blocker.ticket).where(
                Blocker.ticket.has(project_id=project_id)  # type: ignore[arg-type]
            )
        stmt = stmt.order_by(Blocker.escalation_level.desc(), Blocker.detected_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_blocker_for_ticket(self, ticket_id: int) -> Blocker | None:
        stmt = select(Blocker).where(
            and_(
                Blocker.ticket_id == ticket_id,
                Blocker.resolved_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_summary_stats(self) -> dict[str, int | float]:
        """Aggregate stats for the blockers dashboard widget."""
        stmt = select(
            func.count().label("total"),
            func.sum(
                (Blocker.escalation_level == 1).cast(Integer)
            ).label("l1"),
            func.sum(
                (Blocker.escalation_level == 2).cast(Integer)
            ).label("l2"),
            func.sum(
                (Blocker.escalation_level == 3).cast(Integer)
            ).label("l3"),
            func.avg(Blocker.stall_hours).label("avg_stall"),
            func.max(Blocker.stall_hours).label("max_stall"),
        ).where(Blocker.resolved_at.is_(None))
        result = await self.session.execute(stmt)
        row = result.one()
        return {
            "total_open": row.total or 0,
            "level_1": int(row.l1 or 0),
            "level_2": int(row.l2 or 0),
            "level_3": int(row.l3 or 0),
            "avg_stall_hours": float(row.avg_stall or 0),
            "oldest_stall_hours": float(row.max_stall or 0),
        }
