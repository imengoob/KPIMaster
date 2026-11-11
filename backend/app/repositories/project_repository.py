from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def get_by_key(self, key: str) -> Project | None:
        stmt = select(Project).where(Project.key == key.upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_active(self) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.is_active.is_(True))
            .order_by(Project.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_active_sprint(self, project_id: int) -> Project | None:
        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .options(selectinload(Project.sprints))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
