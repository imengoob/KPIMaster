from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company, CompanyPartnership
from app.api.authz import AuthPrincipal

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def setup_companies_data(db: AsyncSession):
    client_co = Company(name="Target Client", slug="tc", tenant_type="client")
    db.add(client_co)
    await db.flush()
    return client_co


async def test_get_partnerships_empty(auth_client: AsyncClient, db: AsyncSession, setup_companies_data, principal_override) -> None:
    client_co = setup_companies_data
    principal_override(AuthPrincipal(user_id=1, username="test", email="test@test.com", role="client_admin", company_id=client_co.id))
    resp = await auth_client.get("/api/v1/companies/me/partnerships")
    assert resp.status_code == 200
    assert resp.json() == []

async def test_create_partnership_success(auth_client: AsyncClient, db: AsyncSession, setup_companies_data, principal_override) -> None:
    client_co = setup_companies_data
    vendor_co = Company(name="Vendor Co", slug="vendor-co", tenant_type="vendor")
    db.add(vendor_co)
    await db.flush()
    principal_override(AuthPrincipal(user_id=1, username="test", email="test@test.com", role="client_admin", company_id=client_co.id))

    resp = await auth_client.post(
        "/api/v1/companies/me/partnerships",
        json={"vendor_company_id": vendor_co.id}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["client_company_id"] == client_co.id
    assert data["vendor_company_id"] == vendor_co.id
    assert data["status"] == "active"
    
    resp_get = await auth_client.get("/api/v1/companies/me/partnerships")
    assert len(resp_get.json()) == 1

async def test_create_partnership_invalid_vendor(auth_client: AsyncClient, db: AsyncSession, setup_companies_data, principal_override) -> None:
    client_co = setup_companies_data
    principal_override(AuthPrincipal(user_id=1, username="test", email="test@test.com", role="client_admin", company_id=client_co.id))
    
    resp = await auth_client.post(
        "/api/v1/companies/me/partnerships",
        json={"vendor_company_id": 9999}
    )
    assert resp.status_code == 400
    assert "Target vendor not found or is not a vendor/ESN." in resp.json()["detail"]

async def test_create_partnership_self_link_fails(auth_client: AsyncClient, db: AsyncSession, setup_companies_data, principal_override) -> None:
    client_co = setup_companies_data
    principal_override(AuthPrincipal(user_id=1, username="test", email="test@test.com", role="client_admin", company_id=client_co.id))
    
    resp = await auth_client.post(
        "/api/v1/companies/me/partnerships",
        json={"vendor_company_id": client_co.id}
    )
    assert resp.status_code == 400
    assert "Target vendor not found or is not a vendor/ESN." in resp.json()["detail"]

async def test_create_partnership_already_exists(auth_client: AsyncClient, db: AsyncSession, setup_companies_data, principal_override) -> None:
    client_co = setup_companies_data
    vendor_co = Company(name="Vendor 2", slug="vendor-2", tenant_type="esn")
    db.add(vendor_co)
    await db.flush()
    
    p = CompanyPartnership(client_company_id=client_co.id, vendor_company_id=vendor_co.id, status="active")
    db.add(p)
    await db.flush()

    principal_override(AuthPrincipal(user_id=1, username="test", email="test@test.com", role="client_admin", company_id=client_co.id))

    resp = await auth_client.post(
        "/api/v1/companies/me/partnerships",
        json={"vendor_company_id": vendor_co.id}
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "active"
