from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.company import Company
from app.models.developer import Developer, DeveloperClientVisibility
from app.models.engagement import Engagement, DeveloperAssignment

from app.api.authz import AuthPrincipal
from app.models.project import Project

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def setup_b2b_data(db: AsyncSession):
    client_co = Company(name="Target Client", slug="tc", tenant_type="client")
    esn_co = Company(name="ESN Provider", slug="esn", tenant_type="esn")
    db.add_all([client_co, esn_co])
    await db.flush()

    dev = Developer(name="B2B Dev", username="b2bdev", email="b2b@test.com", company_id=esn_co.id, is_active=True, role="developer")
    db.add(dev)
    await db.flush()
    return client_co, esn_co, dev


async def test_grant_developer_visibility(auth_client: AsyncClient, db: AsyncSession, setup_b2b_data, test_user, principal_override) -> None:
    client_co, esn_co, dev = setup_b2b_data
    # Make caller SuperAdmin to bypass role checks easily
    principal_override(AuthPrincipal(user_id=1, username="admin", email="admin@test.com", role="super_admin", company_id=None))
    resp = await auth_client.post(
        f"/api/v1/developers/{dev.id}/visibility",
        json={"client_company_id": client_co.id}
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending_developer_approval"
    
async def test_grant_visibility_invalid_client(auth_client: AsyncClient, db: AsyncSession, setup_b2b_data, test_user, principal_override) -> None:
    client_co, esn_co, dev = setup_b2b_data
    principal_override(AuthPrincipal(user_id=1, username="admin", email="admin@test.com", role="super_admin", company_id=None))

    # Try mapping to ESN instead of Client
    resp = await auth_client.post(f"/api/v1/developers/{dev.id}/visibility", json={"client_company_id": esn_co.id})
    assert resp.status_code == 400


async def test_recruiting_pool_only_shows_approved(auth_client: AsyncClient, db: AsyncSession, setup_b2b_data, test_user, principal_override) -> None:
    client_co, esn_co, dev = setup_b2b_data
    principal_override(AuthPrincipal(user_id=2, username="client", email="client@test.com", role="client_admin", company_id=client_co.id))

    # Create pending visibility
    vis = DeveloperClientVisibility(developer_id=dev.id, client_company_id=client_co.id, status="pending_developer_approval")
    db.add(vis)
    await db.flush()

    # Pool should be empty
    resp = await auth_client.get("/api/v1/developers/recruiting/pool")
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # Set to approved
    vis.status = "approved"
    await db.flush()

    resp2 = await auth_client.get("/api/v1/developers/recruiting/pool")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1
    assert resp2.json()[0]["developer"]["id"] == dev.id


async def test_developer_visibility_requests_flow(auth_client: AsyncClient, db: AsyncSession, setup_b2b_data, test_user, principal_override) -> None:
    client_co, esn_co, dev = setup_b2b_data
    principal_override(AuthPrincipal(user_id=3, username="dev", email="dev@test.com", role="developer", company_id=None, developer_id=dev.id))

    vis = DeveloperClientVisibility(developer_id=dev.id, client_company_id=client_co.id, status="pending_developer_approval")
    db.add(vis)
    await db.flush()

    list_resp = await auth_client.get("/api/v1/developers/me/visibility-requests")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    
    app_resp = await auth_client.post(f"/api/v1/developers/me/visibility/{vis.id}/approve")
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "approved"

async def test_developer_history_kpi_extraction(auth_client: AsyncClient, db: AsyncSession, setup_b2b_data, test_user, principal_override) -> None:
    client_co, esn_co, dev = setup_b2b_data
    principal_override(AuthPrincipal(user_id=3, username="dev", email="dev@test.com", role="developer", company_id=None, developer_id=dev.id))
    
    project = Project(name="History Project", key="HPJ")
    db.add(project)
    await db.flush()

    engagement = Engagement(name="Test Eng", client_company_id=client_co.id, vendor_company_id=esn_co.id, project_id=project.id)
    db.add(engagement)
    await db.flush()
    from datetime import date
    assignment = DeveloperAssignment(engagement_id=engagement.id, developer_id=dev.id, start_date=date.today(), assignment_role="Dev")
    db.add(assignment)
    await db.flush()

    resp = await auth_client.get(f"/api/v1/developers/{dev.id}/client-history")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["engagement_name"] == "Test Eng"
    assert "kpis" in items[0]
