import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

sys.path.append("/app")

from app.services.trello.live_project_service import TrelloLiveProjectService

async def main():
    engine = create_async_engine("postgresql+asyncpg://sprintpulse:sprintpulse@postgres:5432/sprintpulse")
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        try:
            live_blockers = await TrelloLiveProjectService(session).list_blockers(52)
            print("Live blockers:", len(live_blockers))
            for b in live_blockers:
                print(b.ticket_title, "Assignee:", b.ticket_assignee_id)
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
