from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import AuthPrincipal
from app.models.company import Company, CompanyProjectAccess
from app.models.developer import Developer
from app.models.engagement import DeveloperAssignment, Engagement
from tests.conftest import project_payload


async def test_create_engagement_creates_company_project_links(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    client_company = Company(name="Client Co", slug="client-co", tenant_type="client", is_active=True)
    vendor_company = Company(name="Vendor Co", slug="vendor-co", tenant_type="vendor", is_active=True)
    db.add_all([client_company, vendor_company])
    await db.flush()

    project = (await client.post("/api/v1/projects", json=project_payload(key="ENG"))).json()

    resp = await client.post(
        "/api/v1/engagements",
        json={
            "name": "Client Co x Vendor Co Squad",
            "client_company_id": client_company.id,
            "vendor_company_id": vendor_company.id,
            "project_id": project["id"],
            "sla_response_hours": 6,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["client_company_name"] == "Client Co"
    assert data["vendor_company_name"] == "Vendor Co"

    links = await db.execute(
        select(CompanyProjectAccess).where(CompanyProjectAccess.project_id == project["id"])
    )
    company_ids = {link.company_id for link in links.scalars().all()}
    assert company_ids == {client_company.id, vendor_company.id}


async def test_client_company_can_list_vendor_developers_assigned_via_engagement(
    client: AsyncClient,
    db: AsyncSession,
    principal_override,
) -> None:
    client_company = Company(name="Bank Client", slug="bank-client", tenant_type="client", is_active=True)
    vendor_company = Company(name="Vendor Squad", slug="vendor-squad", tenant_type="vendor", is_active=True)
    db.add_all([client_company, vendor_company])
    await db.flush()

    project = (await client.post("/api/v1/projects", json=project_payload(key="CVA"))).json()
    db.add_all(
        [
            CompanyProjectAccess(company_id=client_company.id, project_id=project["id"]),
            CompanyProjectAccess(company_id=vendor_company.id, project_id=project["id"]),
        ]
    )
    developer = Developer(
        name="Assigned Vendor Dev",
        email="assigned.vendor@example.com",
        username="assigned-vendor",
        company_id=vendor_company.id,
        trello_member_id="trello_assigned_vendor",
    )
    db.add(developer)
    await db.flush()
    engagement = Engagement(
        name="Bank Client x Vendor Squad",
        client_company_id=client_company.id,
        vendor_company_id=vendor_company.id,
        project_id=project["id"],
        status="active",
        sla_response_hours=8,
        client_visible=True,
    )
    db.add(engagement)
    await db.flush()
    db.add(
        DeveloperAssignment(
            developer_id=developer.id,
            engagement_id=engagement.id,
            assignment_role="developer",
            status="active",
            allocation_percentage=100,
            start_date=date(2026, 1, 1),
            is_primary=True,
        )
    )
    await db.flush()

    principal_override(
        AuthPrincipal(
            user_id=300,
            username="client-pm",
            email="pm@bank-client.test",
            role="client_pm",
            company_id=client_company.id,
            developer_id=None,
        )
    )

    resp = await client.get("/api/v1/developers")
    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()}
    assert "Assigned Vendor Dev" in names


async def test_client_company_cannot_access_unassigned_vendor_developer(
    client: AsyncClient,
    db: AsyncSession,
    principal_override,
) -> None:
    client_company = Company(name="Client A", slug="client-a", tenant_type="client", is_active=True)
    vendor_company = Company(name="Vendor A", slug="vendor-a", tenant_type="vendor", is_active=True)
    db.add_all([client_company, vendor_company])
    await db.flush()

    developer = Developer(
        name="Hidden Vendor Dev",
        email="hidden.vendor@example.com",
        username="hidden-vendor",
        company_id=vendor_company.id,
    )
    db.add(developer)
    await db.flush()

    principal_override(
        AuthPrincipal(
            user_id=301,
            username="client-exec",
            email="exec@client-a.test",
            role="client_exec",
            company_id=client_company.id,
            developer_id=None,
        )
    )

    resp = await client.get(f"/api/v1/developers/{developer.id}")
    assert resp.status_code == 403


async def test_create_assignment_rejects_developer_from_wrong_vendor(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    client_company = Company(name="Client B", slug="client-b", tenant_type="client", is_active=True)
    vendor_company = Company(name="Vendor B", slug="vendor-b", tenant_type="vendor", is_active=True)
    other_vendor = Company(name="Vendor C", slug="vendor-c", tenant_type="vendor", is_active=True)
    db.add_all([client_company, vendor_company, other_vendor])
    await db.flush()

    project = (await client.post("/api/v1/projects", json=project_payload(key="ASG"))).json()
    engagement = Engagement(
        name="Client B x Vendor B",
        client_company_id=client_company.id,
        vendor_company_id=vendor_company.id,
        project_id=project["id"],
        status="active",
        sla_response_hours=8,
        client_visible=True,
    )
    db.add(engagement)
    developer = Developer(
        name="Wrong Vendor Dev",
        email="wrong.vendor@example.com",
        username="wrong-vendor",
        company_id=other_vendor.id,
    )
    db.add(developer)
    await db.flush()

    resp = await client.post(
        f"/api/v1/engagements/{engagement.id}/assignments",
        json={
            "developer_id": developer.id,
            "assignment_role": "developer",
            "allocation_percentage": 100,
            "start_date": "2026-01-10",
        },
    )
    assert resp.status_code == 422
