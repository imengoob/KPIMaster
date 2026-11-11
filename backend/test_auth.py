import pytest
from httpx import AsyncClient
from app.api.authz import AuthPrincipal
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

async def test_x(auth_client: AsyncClient, db: AsyncSession, principal_override):
    principal_override(AuthPrincipal(user_id=1, username="t", email="t", role="company_admin", company_id=1))
    resp = await auth_client.get("/api/v1/companies/me/partnerships")
    assert resp.status_code == 200
