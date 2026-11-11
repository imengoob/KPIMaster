from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.value_objects.priority import SprintStatus
from app.models.sprint import Sprint
from app.repositories.base import BaseRepository


class SprintRepository(BaseRepository[Sprint]):
    model = Sprint

    async def get_active_sprint(self, project_id: int) -> Sprint | None:
        stmt = select(Sprint).where(
            and_(
                Sprint.project_id == project_id,
                Sprint.status == SprintStatus.ACTIVE.value,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_sprint_for_range(
        self,
        project_id: int,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Sprint | None:
        stmt = select(Sprint).where(Sprint.project_id == project_id)
        if start_date is not None:
            stmt = stmt.where(Sprint.end_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(Sprint.start_date <= end_date)
        stmt = stmt.order_by(Sprint.end_date.desc(), Sprint.start_date.desc())
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def get_sprints_for_project(
        self, project_id: int, *, include_tickets: bool = False
    ) -> list[Sprint]:
        stmt = select(Sprint).where(Sprint.project_id == project_id)
        if include_tickets:
            stmt = stmt.options(selectinload(Sprint.tickets))
        stmt = stmt.order_by(Sprint.start_date.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_completed_sprints(
        self,
        project_id: int,
        limit: int = 10,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Sprint]:
        stmt = (
            select(Sprint)
            .where(
                and_(
                    Sprint.project_id == project_id,
                    Sprint.status == SprintStatus.COMPLETED.value,
                )
            )
        )
        if start_date is not None:
            stmt = stmt.where(Sprint.end_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(Sprint.start_date <= end_date)
        stmt = stmt.order_by(Sprint.end_date.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_active_sprints(self) -> list[Sprint]:
        """Used by background workers to scan all active sprints."""
        stmt = (
            select(Sprint)
            .where(Sprint.status == SprintStatus.ACTIVE.value)
            .options(selectinload(Sprint.tickets), selectinload(Sprint.project))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
