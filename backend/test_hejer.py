import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

sys.path.append("/app")

from app.models.user import User
from app.services.developer_kpi_service import DeveloperKPIService

async def main():
    engine = create_async_engine("postgresql+asyncpg://sprintpulse:sprintpulse@postgres:5432/sprintpulse")
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        hejer = await session.scalar(select(User).where(User.username == 'hejer_dev'))
        if hejer:
            try:
                report = await DeveloperKPIService(session).compute_developer_kpis(12, 52, None)
                print("Report computed OK! Status:", report.status)
            except Exception as e:
                print("Report computation FAIL:", e)

if __name__ == "__main__":
    asyncio.run(main())
