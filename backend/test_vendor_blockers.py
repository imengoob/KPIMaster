import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

sys.path.append("/app")

from app.models.company import Company
from app.models.engagement import Engagement, DeveloperAssignment
from app.models.developer import Developer
from app.api.authz import AuthPrincipal

async def main():
    engine = create_async_engine("postgresql+asyncpg://sprintpulse:sprintpulse@postgres:5432/sprintpulse")
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        principal = AuthPrincipal(user_id=1, username="test", email="test", role="esn_admin", company_id=8, developer_id=None, kpi_subject_id=None)
        
        # Test my proposed query
        stmt = (
            select(Developer.id, Developer.trello_member_id)
            .distinct()
            .join(DeveloperAssignment, DeveloperAssignment.developer_id == Developer.id, isouter=True)
            .join(Engagement, Engagement.vendor_company_id == Developer.company_id)
            .where(
                Developer.company_id == principal.company_id,
                Engagement.vendor_company_id == principal.company_id,
                Engagement.status == "active",
                Engagement.project_id == 61
            )
        )
        res = await session.execute(stmt)
        devs = res.all()
        print("Vendor Developers for project 61:", devs)

if __name__ == "__main__":
    asyncio.run(main())
