"""
Integration tests for /api/v1/developers.

Covers:
- Developer CRUD
- Duplicate email rejection
- Active-only filter
- Per-sprint progress report
- BackendDeveloper interface contract
"""
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import AuthPrincipal
from app.models.trello_action import TrelloAction
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard
from app.models.company import Company, CompanyProjectAccess
from app.models.developer import Developer
from app.models.developer_external_identity import DeveloperExternalIdentity
from app.models.engagement import DeveloperAssignment, Engagement
from app.models.integration_account import IntegrationAccount
from app.models.integration_task import IntegrationComment, IntegrationTask
from app.models.trello_credential import TrelloCredential
from app.models.trello_list import ListType, TrelloList
from app.models.user import User
from app.services.developer_kpi_service import DeveloperKPIService

from tests.conftest import developer_payload, ticket_payload


# ── Create ────────────────────────────────────────────────────────────────────

async def test_create_developer_returns_201(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/developers", json=developer_payload())
    assert resp.status_code == 201


async def test_create_developer_response_matches_frontend_contract(
    client: AsyncClient,
) -> None:
    """Fields must match frontend BackendDeveloper interface."""
    resp = await client.post("/api/v1/developers", json=developer_payload(email="z@x.com"))
    data = resp.json()
    expected_fields = {
        "id", "name", "email", "username", "team", "role",
        "slack_id", "github_username", "is_active",
        "created_at", "updated_at",
    }
    assert expected_fields.issubset(data.keys()), (
        f"Missing fields: {expected_fields - data.keys()}"
    )


async def test_create_developer_duplicate_email_returns_409(
    client: AsyncClient,
) -> None:
    email = "dup@test.com"
    await client.post("/api/v1/developers", json=developer_payload(email=email))
    resp = await client.post(
        "/api/v1/developers", json=developer_payload(email=email, username="dup2")
    )
    assert resp.status_code == 409


async def test_create_developer_persists_fields(client: AsyncClient) -> None:
    payload = developer_payload(
        name="Bob Dev",
        email="bob@test.com",
        role="lead",
        team="frontend",
        github_username="bobdev",
    )
    data = (await client.post("/api/v1/developers", json=payload)).json()
    assert data["name"] == "Bob Dev"
    assert data["role"] == "lead"
    assert data["team"] == "frontend"
    assert data["github_username"] == "bobdev"
    assert data["is_active"] is True


async def test_company_scope_filters_developer_list(
    client: AsyncClient,
    db: AsyncSession,
    principal_override,
) -> None:
    company = Company(name="Scoped Co", slug="scoped-co", is_active=True)
    db.add(company)
    await db.flush()

    own = Developer(
        name="Scoped Dev",
        email="scoped@example.com",
        username="scoped-dev",
        company_id=company.id,
    )
    foreign = Developer(
        name="Foreign Dev",
        email="foreign@example.com",
        username="foreign-dev",
    )
    db.add_all([own, foreign])
    await db.flush()

    principal_override(
        AuthPrincipal(
            user_id=101,
            username="manager",
            email="manager@scoped.test",
            role="company_manager",
            company_id=company.id,
            developer_id=None,
        )
    )

    resp = await client.get("/api/v1/developers")
    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()}
    assert "Scoped Dev" in names
    assert "Foreign Dev" not in names


async def test_vendor_scope_hides_client_internal_developers(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
    principal_override,
) -> None:
    client_company = Company(name="Client Internal", slug="client-internal", tenant_type="client")
    vendor_company = Company(name="Vendor Only", slug="vendor-only", tenant_type="vendor")
    db.add_all([client_company, vendor_company])
    await db.flush()

    external_dev = Developer(
        name="External Vendor Dev",
        email="external.vendor@example.com",
        username="external-vendor",
        company_id=vendor_company.id,
        trello_member_id="external_member",
    )
    internal_dev = Developer(
        name="Client Internal Dev",
        email="internal.client@example.com",
        username="internal-client",
        company_id=client_company.id,
        trello_member_id="internal_member",
    )
    db.add_all([external_dev, internal_dev])
    await db.flush()

    engagement = Engagement(
        name="Vendor engagement",
        client_company_id=client_company.id,
        vendor_company_id=vendor_company.id,
        project_id=existing_project["id"],
    )
    db.add(engagement)
    await db.flush()
    db.add_all([
        DeveloperAssignment(
            developer_id=external_dev.id,
            engagement_id=engagement.id,
            start_date=date(2026, 4, 1),
        ),
        DeveloperAssignment(
            developer_id=internal_dev.id,
            engagement_id=engagement.id,
            start_date=date(2026, 4, 1),
        ),
    ])
    await db.flush()

    principal_override(
        AuthPrincipal(
            user_id=120,
            username="vendor",
            email="vendor@example.com",
            role="esn_delivery_manager",
            company_id=vendor_company.id,
            developer_id=None,
        )
    )

    resp = await client.get("/api/v1/developers")
    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()}
    assert "External Vendor Dev" in names
    assert "Client Internal Dev" not in names


async def test_vendor_team_kpis_empty_when_no_external_developers_assigned(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
    principal_override,
) -> None:
    project_id = existing_project["id"]
    now = datetime.now(UTC)

    client_company = Company(name="Client No Vendor", slug="client-no-vendor", tenant_type="client")
    vendor_company = Company(name="Vendor Empty", slug="vendor-empty", tenant_type="vendor")
    db.add_all([client_company, vendor_company])
    await db.flush()
    db.add(CompanyProjectAccess(company_id=vendor_company.id, project_id=project_id))

    internal_dev = Developer(
        name="Internal Only Dev",
        email="internal.only@example.com",
        username="internal-only",
        company_id=client_company.id,
        trello_member_id="client_internal_member",
    )
    db.add(internal_dev)
    await db.flush()

    engagement = Engagement(
        name="Internal-only engagement",
        client_company_id=client_company.id,
        vendor_company_id=vendor_company.id,
        project_id=project_id,
    )
    db.add(engagement)
    await db.flush()
    db.add(DeveloperAssignment(
        developer_id=internal_dev.id,
        engagement_id=engagement.id,
        start_date=date(2026, 4, 1),
    ))
    await db.flush()

    credential = TrelloCredential(project_id=project_id, api_key="key", api_token="token", is_active=True)
    db.add(credential)
    await db.flush()
    board = TrelloBoard(
        credential_id=credential.id,
        trello_id="board_internal_only",
        name="Internal Board",
        last_synced_at=now,
        is_closed=False,
    )
    db.add(board)
    await db.flush()
    trello_list = TrelloList(
        board_id=board.id,
        trello_id="list_internal",
        name="Doing",
        pos=1,
        list_type=ListType.WIP,
        is_closed=False,
    )
    db.add(trello_list)
    await db.flush()
    db.add(TrelloCard(
        board_id=board.id,
        list_id=trello_list.id,
        trello_id="card_internal_only",
        trello_short_id=1,
        name="Client internal implementation",
        member_ids=["client_internal_member"],
        labels=[{"name": "feature 3sp"}],
        trello_last_activity=now,
        is_closed=False,
    ))
    await db.flush()

    principal_override(AuthPrincipal(
        user_id=121,
        username="vendor-empty",
        email="vendor-empty@example.com",
        role="esn_delivery_manager",
        company_id=vendor_company.id,
        developer_id=None,
    ))

    team_resp = await client.get(f"/api/v1/developers/team-kpis?project_id={project_id}")
    assert team_resp.status_code == 200, team_resp.text
    team = team_resp.json()
    assert team["members"] == []
    assert team["warning_signals"] == []
    assert team["team_completion_rate"] == 0.0

    client_resp = await client.get(f"/api/v1/developers/client-progress?project_id={project_id}")
    assert client_resp.status_code == 200, client_resp.text
    client_report = client_resp.json()
    assert client_report["members"] == []
    assert client_report["summary"]["total_developers"] == 0
    assert client_report["summary"]["story_points_total"] == 0


async def test_vendor_team_kpis_uses_external_identity_without_leaking_internal_devs(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
    principal_override,
) -> None:
    project_id = existing_project["id"]
    now = datetime.now(UTC)

    client_company = Company(name="Client External Identity", slug="client-ext-id", tenant_type="client")
    vendor_company = Company(name="Vendor External Identity", slug="vendor-ext-id", tenant_type="vendor")
    db.add_all([client_company, vendor_company])
    await db.flush()
    db.add(CompanyProjectAccess(company_id=vendor_company.id, project_id=project_id))

    external_dev = Developer(
        name="Mapped Vendor Dev",
        email="mapped.vendor@example.com",
        username="mapped-vendor",
        company_id=vendor_company.id,
    )
    internal_dev = Developer(
        name="Mapped Internal Dev",
        email="mapped.internal@example.com",
        username="mapped-internal",
        company_id=client_company.id,
    )
    db.add_all([external_dev, internal_dev])
    await db.flush()

    engagement = Engagement(
        name="External identity engagement",
        client_company_id=client_company.id,
        vendor_company_id=vendor_company.id,
        project_id=project_id,
    )
    db.add(engagement)
    await db.flush()
    db.add_all([
        DeveloperAssignment(
            developer_id=external_dev.id,
            engagement_id=engagement.id,
            start_date=date(2026, 4, 1),
        ),
        DeveloperAssignment(
            developer_id=internal_dev.id,
            engagement_id=engagement.id,
            start_date=date(2026, 4, 1),
        ),
    ])

    user = User(
        username="trello-owner",
        email="trello-owner@example.com",
        password_hash="hashed",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    account = IntegrationAccount(
        user_id=user.id,
        provider="trello",
        account_name="Trello",
        external_account_id="trello-owner-id",
        scopes=[],
        extra_data={},
        is_active=True,
    )
    db.add(account)
    await db.flush()

    db.add_all([
        DeveloperExternalIdentity(
            developer_id=external_dev.id,
            integration_account_id=account.id,
            provider="trello",
            external_user_id="vendor_member_ext",
        ),
        DeveloperExternalIdentity(
            developer_id=internal_dev.id,
            integration_account_id=account.id,
            provider="trello",
            external_user_id="internal_member_ext",
        ),
    ])
    await db.flush()

    db.add_all([
        IntegrationTask(
            account_id=account.id,
            project_id=project_id,
            provider="trello",
            board_id="board_ext_identity",
            external_task_id="card_vendor",
            title="Vendor delivery card",
            status="in_progress",
            task_type="task",
            assignee_ids=["vendor_member_ext"],
            labels=[],
            story_points=5,
            external_created_at=now - timedelta(days=1),
            external_updated_at=now,
            last_synced_at=now,
            is_active=True,
        ),
        IntegrationTask(
            account_id=account.id,
            project_id=project_id,
            provider="trello",
            board_id="board_ext_identity",
            external_task_id="card_internal",
            title="Client internal card",
            status="in_progress",
            task_type="task",
            assignee_ids=["internal_member_ext"],
            labels=[],
            story_points=8,
            external_created_at=now - timedelta(days=1),
            external_updated_at=now,
            last_synced_at=now,
            is_active=True,
        ),
    ])
    await db.flush()

    principal_override(AuthPrincipal(
        user_id=122,
        username="vendor-ext-id",
        email="vendor-ext-id@example.com",
        role="esn_delivery_manager",
        company_id=vendor_company.id,
        developer_id=None,
    ))

    resp = await client.get(f"/api/v1/developers/team-kpis?project_id={project_id}")
    assert resp.status_code == 200, resp.text
    names = {member["developer_name"] for member in resp.json()["members"]}
    assert names == {"Mapped Vendor Dev"}


async def test_vendor_can_match_developer_by_full_name_to_trello_member(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
    principal_override,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas.trello import TrelloAPIMember
    from app.services.trello.client import TrelloClient

    project_id = existing_project["id"]
    client_company = Company(name="Client Match", slug="client-match", tenant_type="client")
    vendor_company = Company(name="Vendor Match", slug="vendor-match", tenant_type="vendor")
    db.add_all([client_company, vendor_company])
    await db.flush()
    db.add(CompanyProjectAccess(company_id=vendor_company.id, project_id=project_id))

    engagement = Engagement(
        name="Vendor Match Engagement",
        client_company_id=client_company.id,
        vendor_company_id=vendor_company.id,
        project_id=project_id,
    )
    db.add(engagement)
    credential = TrelloCredential(project_id=project_id, api_key="key", api_token="token", is_active=True)
    db.add(credential)
    await db.flush()
    db.add(TrelloBoard(
        credential_id=credential.id,
        trello_id="board_match",
        name="Match Board",
        is_closed=False,
        last_synced_at=datetime.now(UTC),
    ))
    await db.flush()

    async def fake_get_board_members(self, board_id: str):
        assert board_id == "board_match"
        return [
            TrelloAPIMember(id="trello_alice", fullName="Alice Chen", username="alicechen"),
            TrelloAPIMember(id="trello_bob", fullName="Bob Martin", username="bobm"),
        ]

    monkeypatch.setattr(TrelloClient, "get_board_members", fake_get_board_members)
    principal_override(AuthPrincipal(
        user_id=123,
        username="vendor-match",
        email="vendor-match@example.com",
        role="esn_delivery_manager",
        company_id=vendor_company.id,
        developer_id=None,
    ))

    candidates_resp = await client.get(
        f"/api/v1/developers/trello-member-candidates?project_id={project_id}&full_name=Alice%20Chen"
    )
    assert candidates_resp.status_code == 200, candidates_resp.text
    assert candidates_resp.json()[0]["trello_member_id"] == "trello_alice"

    save_resp = await client.post(
        "/api/v1/developers/vendor-profile",
        json={
            "full_name": "Alice Chen",
            "engagement_id": engagement.id,
            "role": "frontend developer",
        },
    )
    assert save_resp.status_code == 201, save_resp.text
    payload = save_resp.json()
    assert payload["matched_trello_member_id"] == "trello_alice"
    assert payload["match_source"] == "exact_name"
    assert payload["developer"]["company_id"] == vendor_company.id

    identity = await db.scalar(
        select(DeveloperExternalIdentity).where(
            DeveloperExternalIdentity.external_user_id == "trello_alice",
            DeveloperExternalIdentity.provider == "trello",
        )
    )
    assert identity is not None
    assignment = await db.scalar(
        select(DeveloperAssignment).where(
            DeveloperAssignment.developer_id == payload["developer"]["id"],
            DeveloperAssignment.engagement_id == engagement.id,
        )
    )
    assert assignment is not None


# ── Read ──────────────────────────────────────────────────────────────────────

async def test_get_developer_by_id(client: AsyncClient, existing_developer: dict) -> None:
    dev_id = existing_developer["id"]
    resp = await client.get(f"/api/v1/developers/{dev_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == dev_id


async def test_get_nonexistent_developer_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/developers/99999")
    assert resp.status_code == 404


async def test_developer_account_can_only_access_its_own_kpi_subject(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
    principal_override,
) -> None:
    company = Company(name="Dev Co", slug="dev-co", is_active=True)
    db.add(company)
    await db.flush()

    developer = Developer(
        name="Alice KPI",
        email="alice.kpi@example.com",
        username="alice-kpi",
        company_id=company.id,
        trello_member_id="trello_member_alice",
    )
    db.add(developer)
    await db.flush()

    user = User(
        username="alice-account",
        email="alice.account@example.com",
        password_hash="hashed",
        role="developer",
        company_id=company.id,
        developer_id=developer.id,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()

    principal_override(
        AuthPrincipal(
            user_id=user.id,
            username=user.username,
            email=user.email,
            role="developer",
            company_id=company.id,
            developer_id=developer.id,
        )
    )

    resp = await client.get(
        f"/api/v1/developers/99999999/kpis?project_id={existing_project['id']}"
    )
    assert resp.status_code == 403


# ── List ──────────────────────────────────────────────────────────────────────

async def test_list_developers_returns_array(client: AsyncClient) -> None:
    await client.post("/api/v1/developers", json=developer_payload(email="d1@t.com", username="u1"))
    await client.post("/api/v1/developers", json=developer_payload(email="d2@t.com", username="u2"))
    resp = await client.get("/api/v1/developers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 2


async def test_list_developers_active_only_filter(client: AsyncClient) -> None:
    """active_only=false must include inactive developers too."""
    dev_resp = await client.post(
        "/api/v1/developers",
        json=developer_payload(email="inactive@t.com", username="inactive_u"),
    )
    dev_id = dev_resp.json()["id"]
    # Deactivate
    await client.patch(f"/api/v1/developers/{dev_id}", json={"is_active": False})

    active = await client.get("/api/v1/developers?active_only=true")
    all_devs = await client.get("/api/v1/developers?active_only=false")

    active_ids = {d["id"] for d in active.json()}
    all_ids = {d["id"] for d in all_devs.json()}

    assert dev_id not in active_ids
    assert dev_id in all_ids


# ── Update ────────────────────────────────────────────────────────────────────

async def test_update_developer_role(
    client: AsyncClient, existing_developer: dict
) -> None:
    dev_id = existing_developer["id"]
    resp = await client.patch(f"/api/v1/developers/{dev_id}", json={"role": "lead"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "lead"


async def test_update_nonexistent_developer_returns_404(client: AsyncClient) -> None:
    resp = await client.patch("/api/v1/developers/99999", json={"role": "lead"})
    assert resp.status_code == 404


# ── Progress report ───────────────────────────────────────────────────────────

async def test_developer_progress_report_shape(
    client: AsyncClient,
    existing_developer: dict,
    existing_sprint: dict,
) -> None:
    dev_id = existing_developer["id"]
    sprint_id = existing_sprint["id"]
    resp = await client.get(f"/api/v1/developers/{dev_id}/progress/{sprint_id}")
    assert resp.status_code == 200
    data = resp.json()
    expected = {
        "developer_id", "developer_name",
        "assigned_tickets", "completed_tickets",
        "in_progress_tickets", "blocked_tickets",
        "total_estimated_hours", "total_actual_hours",
        "estimation_accuracy", "on_track",
    }
    assert expected.issubset(data.keys())


async def test_developer_progress_empty_sprint(
    client: AsyncClient,
    existing_developer: dict,
    existing_sprint: dict,
) -> None:
    dev_id = existing_developer["id"]
    sprint_id = existing_sprint["id"]
    resp = await client.get(f"/api/v1/developers/{dev_id}/progress/{sprint_id}")
    data = resp.json()
    assert data["assigned_tickets"] == 0
    assert data["completed_tickets"] == 0
    assert data["estimation_accuracy"] == 1.0
    assert data["on_track"] is False  # no tickets in progress = not on_track


async def test_developer_progress_with_tickets(
    client: AsyncClient,
    existing_developer: dict,
    existing_project: dict,
    existing_sprint: dict,
) -> None:
    dev_id = existing_developer["id"]
    pid = existing_project["id"]
    sprint_id = existing_sprint["id"]

    # Assign tickets to this developer in this sprint
    for status in ("done", "done", "in_progress"):
        await client.post(
            "/api/v1/tickets",
            json=ticket_payload(
                pid,
                title=f"Task {status}",
                status=status,
                assignee_id=dev_id,
                sprint_id=sprint_id,
                estimated_hours=4.0,
                actual_hours=4.0 if status == "done" else None,
            ),
        )

    resp = await client.get(f"/api/v1/developers/{dev_id}/progress/{sprint_id}")
    data = resp.json()
    assert data["assigned_tickets"] == 3
    assert data["completed_tickets"] == 2
    assert data["in_progress_tickets"] == 1


async def test_client_progress_returns_empty_report_without_trello_board(
    client: AsyncClient,
    existing_project: dict,
) -> None:
    resp = await client.get(f"/api/v1/developers/client-progress?project_id={existing_project['id']}")
    assert resp.status_code == 200

    data = resp.json()
    assert data["project_id"] == existing_project["id"]
    assert data["members"] == []
    assert data["summary"]["total_developers"] == 0
    assert data["summary"]["overall_completion_rate"] == 0.0


async def test_register_company_account_returns_role_and_company_context(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "company_owner",
            "email": "owner@company.example",
            "password": "StrongPass123!",
            "company_name": "Owner Company",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["role"] == "company_admin"
    assert data["company_name"] == "Owner Company"
    assert data["company_slug"] == "owner-company"


async def test_client_progress_aggregates_client_facing_delivery_metrics(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = existing_project["id"]
    now = datetime.now(UTC)

    credential = TrelloCredential(
        project_id=project_id,
        api_key="key",
        api_token="token",
        is_active=True,
    )
    db.add(credential)
    await db.flush()

    board = TrelloBoard(
        credential_id=credential.id,
        trello_id="board_123",
        name="Client Delivery Board",
        last_synced_at=now,
        is_closed=False,
    )
    db.add(board)
    await db.flush()

    done_list = TrelloList(
        board_id=board.id,
        trello_id="list_done",
        name="Done",
        pos=1,
        list_type=ListType.DONE,
        is_closed=False,
    )
    wip_list = TrelloList(
        board_id=board.id,
        trello_id="list_wip",
        name="Doing",
        pos=2,
        list_type=ListType.WIP,
        is_closed=False,
    )
    db.add_all([done_list, wip_list])
    await db.flush()

    alice_id = "member_alice"
    bob_id = "member_bob"
    carla_id = "member_carla"

    cards = [
        TrelloCard(
            board_id=board.id,
            list_id=done_list.id,
            trello_id="card_1",
            trello_short_id=1,
            name="Delivered feature",
            member_ids=[alice_id],
            labels=[{"name": "feature 5sp"}],
            cycle_time_hours=8,
            trello_last_activity=now - timedelta(hours=12),
            entered_wip_at=now - timedelta(days=4),
            entered_done_at=now - timedelta(days=1),
            is_closed=False,
            due_complete=True,
        ),
        TrelloCard(
            board_id=board.id,
            list_id=wip_list.id,
            trello_id="card_2",
            trello_short_id=2,
            name="Blocked API task",
            member_ids=[alice_id],
            labels=[{"name": "bug 3sp"}],
            trello_last_activity=now - timedelta(hours=5),
            entered_wip_at=now - timedelta(days=2),
            is_stalled=True,
            stalled_since=now - timedelta(hours=20),
            is_closed=False,
        ),
        TrelloCard(
            board_id=board.id,
            list_id=done_list.id,
            trello_id="card_3",
            trello_short_id=3,
            name="Completed client fix",
            member_ids=[bob_id],
            labels=[{"name": "feature 2sp"}],
            cycle_time_hours=6,
            trello_last_activity=now - timedelta(days=2),
            entered_wip_at=now - timedelta(days=6),
            entered_done_at=now - timedelta(days=2),
            is_closed=False,
            due_complete=True,
        ),
        TrelloCard(
            board_id=board.id,
            list_id=wip_list.id,
            trello_id="card_4",
            trello_short_id=4,
            name="In-flight refinement",
            member_ids=[bob_id],
            labels=[{"name": "task 3sp"}],
            trello_last_activity=now - timedelta(days=2),
            entered_wip_at=now - timedelta(days=3),
            is_closed=False,
        ),
        TrelloCard(
            board_id=board.id,
            list_id=done_list.id,
            trello_id="card_5",
            trello_short_id=5,
            name="Completed reporting",
            member_ids=[carla_id],
            labels=[{"name": "feature 8sp"}],
            cycle_time_hours=4,
            trello_last_activity=now - timedelta(days=8),
            entered_wip_at=now - timedelta(days=10),
            entered_done_at=now - timedelta(days=8),
            is_closed=False,
            due_complete=True,
        ),
    ]
    db.add_all(cards)
    await db.flush()

    db.add(
        TrelloAction(
            card_id=cards[1].id,
            trello_action_id="act_1",
            action_type="commentCard",
            action_date=now - timedelta(hours=6),
            data={"text": "Blocked waiting for confirmation?"},
            trello_member_id=alice_id,
            member_name="Alice Chen",
        )
    )
    await db.flush()

    async def fake_build_name_map(self, board, project_id):
        return {
            alice_id: "Alice Chen",
            bob_id: "Bob Martin",
            carla_id: "Carla Diaz",
        }

    monkeypatch.setattr(DeveloperKPIService, "_build_name_map", fake_build_name_map)

    resp = await client.get(f"/api/v1/developers/client-progress?project_id={project_id}")
    assert resp.status_code == 200

    data = resp.json()
    summary = data["summary"]
    members = data["members"]

    assert summary["total_developers"] == 3
    assert summary["behind_count"] == 1
    assert summary["at_risk_count"] == 1
    assert summary["on_track_count"] == 1
    assert summary["overall_completion_rate"] == 0.6
    assert summary["story_points_completed"] == 15
    assert summary["story_points_total"] == 21
    assert summary["active_blockers"] == 1
    assert summary["avg_cycle_time_hours"] == 6.0

    assert [member["developer_name"] for member in members] == [
        "Alice Chen",
        "Bob Martin",
        "Carla Diaz",
    ]

    alice = members[0]
    assert alice["status"] == "behind"
    assert alice["tickets_completed"] == 1
    assert alice["tickets_total"] == 2
    assert alice["active_work_items"] == 1
    assert alice["active_blockers"] == 1
    assert alice["activity_freshness"] == "active"
    assert "slowing delivery" in alice["risk_note"]

    bob = members[1]
    assert bob["status"] == "at-risk"
    assert bob["tickets_completed"] == 1
    assert bob["tickets_total"] == 2
    assert bob["activity_freshness"] == "recent"
    assert "closer monitoring" in bob["risk_note"]

    carla = members[2]
    assert carla["status"] == "on-track"
    assert carla["tickets_completed"] == 1
    assert carla["tickets_total"] == 1
    assert carla["activity_freshness"] == "stale"
    assert carla["risk_note"] is None


async def test_team_kpis_use_normalized_jira_tasks_and_comment_response_metrics(
    client: AsyncClient,
    db: AsyncSession,
    existing_project: dict,
) -> None:
    project_id = existing_project["id"]
    now = datetime.now(UTC)

    client_company = Company(name="Client X", slug="client-x", tenant_type="client")
    vendor_company = Company(name="Vendor Co", slug="vendor-co", tenant_type="vendor")
    db.add_all([client_company, vendor_company])
    await db.flush()

    developer = Developer(
        name="Jira Developer",
        email="jira.dev@example.com",
        username="jira-dev",
        company_id=vendor_company.id,
    )
    db.add(developer)
    await db.flush()

    engagement = Engagement(
        name="Client X Delivery",
        client_company_id=client_company.id,
        vendor_company_id=vendor_company.id,
        project_id=project_id,
        sla_response_hours=4,
    )
    db.add(engagement)
    await db.flush()
    db.add(DeveloperAssignment(
        developer_id=developer.id,
        engagement_id=engagement.id,
        start_date=date(2026, 4, 1),
    ))

    user = User(
        username="integration-owner",
        email="integration-owner@example.com",
        password_hash="hashed",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    account = IntegrationAccount(
        user_id=user.id,
        provider="jira",
        account_name="Client X Jira",
        external_account_id="cloud-1",
        scopes=[],
        extra_data={},
        is_active=True,
    )
    db.add(account)
    await db.flush()

    db.add(DeveloperExternalIdentity(
        developer_id=developer.id,
        integration_account_id=account.id,
        provider="jira",
        external_user_id="jira-user-1",
        external_display_name="Jira Developer",
    ))
    await db.flush()

    task = IntegrationTask(
        account_id=account.id,
        project_id=project_id,
        provider="jira",
        board_id="SCRUM",
        external_task_id="JIRA-1",
        title="Implement client workflow",
        status="in_progress",
        task_type="story",
        assignee_ids=["jira-user-1"],
        labels=[],
        story_points=5,
        external_created_at=now - timedelta(days=1),
        external_updated_at=now - timedelta(hours=1),
        last_synced_at=now,
        is_active=True,
    )
    blocked = IntegrationTask(
        account_id=account.id,
        project_id=project_id,
        provider="jira",
        board_id="SCRUM",
        external_task_id="JIRA-2",
        title="Blocked API handoff",
        status="blocked",
        task_type="task",
        assignee_ids=["jira-user-1"],
        labels=["blocked"],
        story_points=3,
        external_created_at=now - timedelta(days=2),
        external_updated_at=now - timedelta(hours=8),
        last_synced_at=now,
        is_active=True,
    )
    db.add_all([task, blocked])
    await db.flush()

    db.add_all([
        IntegrationComment(
            task_id=task.id,
            account_id=account.id,
            provider="jira",
            external_comment_id="c1",
            external_task_id="JIRA-1",
            author_external_id="teammate-1",
            author_name="Team Mate",
            body="Can you confirm the API shape?",
            external_created_at=now - timedelta(hours=5),
        ),
        IntegrationComment(
            task_id=task.id,
            account_id=account.id,
            provider="jira",
            external_comment_id="c2",
            external_task_id="JIRA-1",
            author_external_id="jira-user-1",
            author_name="Jira Developer",
            body="Confirmed, I updated the payload.",
            external_created_at=now - timedelta(hours=2),
        ),
    ])
    await db.flush()

    resp = await client.get(f"/api/v1/developers/team-kpis?project_id={project_id}")
    assert resp.status_code == 200, resp.text
    member = resp.json()["members"][0]
    assert member["developer_id"] == developer.id
    assert member["provider_sources"] == ["jira"]
    assert member["ert_target_hours"] == 4
    assert member["ert_status"] == "within-target"
    assert member["question_response_time_hours"] == 3.0
    assert member["active_blockers"] == 1

    detail_resp = await client.get(f"/api/v1/developers/{developer.id}/kpis?project_id={project_id}")
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()
    assert detail["client_name"] == "Client X"
    assert detail["engagement_name"] == "Client X Delivery"
    assert detail["comment_response_time_hours"] == 3.0
    assert detail["unanswered_questions_count"] == 0
    metrics = {item["ticket_id"]: item for item in detail["ticket_response_metrics"]}
    assert metrics["JIRA-1"]["response_time_hours"] == 3.0
    assert metrics["JIRA-2"]["blocker_status"] == "blocked"
