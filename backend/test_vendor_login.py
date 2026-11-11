import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

import sys
sys.path.append("/app")

from app.models.user import User

async def main():
    engine = create_async_engine("postgresql+asyncpg://sprintpulse:sprintpulse@postgres:5432/sprintpulse")
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.username == 'tawssil_admin'))
        print(user.role if user else "Not found")

if __name__ == "__main__":
    asyncio.run(main())
