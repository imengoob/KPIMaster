import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

import asgi_lifespan
from httpx import AsyncClient

sys.path.append("/home/khaled/Desktop/lovable_project/sprint tracker/backend")
from app.main import app

async def main():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        login = await ac.post("/api/v1/auth/login", json={"username": "tawssil_admin", "password": "password"})
        print("Login:", login.json())
        token = login.json().get("access_token")
        
        headers = {"Authorization": f"Bearer {token}"}
        res = await ac.get("/api/v1/developers/team-kpis?project_id=1", headers=headers)
        print("KPIs:", res.status_code, res.json())

if __name__ == "__main__":
    asyncio.run(main())
