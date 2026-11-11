import pytest
from httpx import AsyncClient

from app.api.authz import AuthPrincipal
from app.models.company import Company


async def test_get_my_company(client: AsyncClient, db, principal_override) -> None:
    company = Company(name="Test Co", slug="test-co", tenant_type="esn", is_active=True)
    db.add(company)
    await db.flush()

    principal_override(
        AuthPrincipal(
            user_id=1,
            username="admin",
            email="admin@example.com",
            role="company_admin",
            company_id=company.id,
            developer_id=None,
        )
    )

    resp = await client.get("/api/v1/companies/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Co"
    assert data["slug"] == "test-co"


async def test_update_my_company(client: AsyncClient, db, principal_override) -> None:
    company = Company(name="Old Name", slug="old-name", tenant_type="esn", is_active=True)
    db.add(company)
    await db.flush()

    principal_override(
        AuthPrincipal(
            user_id=1,
            username="admin",
            email="admin@example.com",
            role="company_admin",
            company_id=company.id,
            developer_id=None,
        )
    )

    payload = {"name": "New Name"}
    resp = await client.patch("/api/v1/companies/me", json=payload)
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
