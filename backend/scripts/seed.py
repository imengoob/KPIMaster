"""
Database seed script — creates realistic demo data.

Usage:
    cd backend/
    python scripts/seed.py

Creates:
  - 3 projects (Phoenix, Atlas, Nova)
  - 3 developers per project
  - 2 sprints per project (1 completed, 1 active)
  - ~10 tickets per sprint (various statuses, priorities, types)
  - Blockers on stalled tickets
  - Repository activity records with some mismatches
"""
from __future__ import annotations

import asyncio
import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

# Add parent dir to path so imports work from scripts/
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password
from app.database import AsyncSessionLocal, engine
from app.models import Base
from app.models.blocker import Blocker
from app.models.burndown_entry import BurndownEntry
from app.models.company import Company, CompanyProjectAccess
from app.models.developer import Developer
from app.models.engagement import DeveloperAssignment, Engagement
from app.models.kpi_snapshot import KPISnapshot
from app.models.project import Project
from app.models.repository_activity import RepositoryActivity
from app.models.sprint import Sprint
from app.models.ticket import Ticket
from app.models.trello_action import TrelloAction
from app.models.trello_board import TrelloBoard
from app.models.trello_card import TrelloCard
from app.models.trello_credential import TrelloCredential
from app.models.trello_list import ListType, TrelloList
from app.models.user import User

rng = random.Random(42)  # Deterministic seed

# ── Data templates ────────────────────────────────────────────────────────────

COMPANIES = [
    {
        "name": "Banque Horizon",
        "slug": "banque-horizon",
        "tenant_type": "client",
        "description": "French banking group modernising customer-facing delivery governance.",
        "contact_email": "delivery@banque-horizon.fr",
    },
    {
        "name": "Retail One",
        "slug": "retail-one",
        "tenant_type": "client",
        "description": "Retail program office coordinating omnichannel product delivery.",
        "contact_email": "pm-office@retail-one.fr",
    },
    {
        "name": "HexaDev",
        "slug": "hexadev",
        "tenant_type": "vendor",
        "description": "Paris-based ESN delivering product squads for regulated clients.",
        "contact_email": "ops@hexadev.fr",
    },
    {
        "name": "NovaForge",
        "slug": "novaforge",
        "tenant_type": "vendor",
        "description": "Delivery-focused ESN specialising in analytics and internal tooling.",
        "contact_email": "staffing@novaforge.fr",
    },
]

PROJECTS = [
    {
        "name": "Project Phoenix",
        "key": "PHX",
        "description": "Customer-facing web platform rebuild",
        "repository_url": "https://github.com/banque-horizon/phoenix",
        "slack_channel": "#phoenix",
        "client_slug": "banque-horizon",
        "vendor_slug": "hexadev",
        "engagement_name": "Banque Horizon x HexaDev Core Platform",
        "developer_usernames": ["alice", "bob", "carol"],
    },
    {
        "name": "Project Atlas",
        "key": "ATL",
        "description": "Internal analytics and reporting suite",
        "repository_url": "https://github.com/banque-horizon/atlas",
        "slack_channel": "#atlas",
        "client_slug": "banque-horizon",
        "vendor_slug": "novaforge",
        "engagement_name": "Banque Horizon x NovaForge Reporting Factory",
        "developer_usernames": ["david", "eva", "frank"],
    },
    {
        "name": "Project Nova",
        "key": "NOV",
        "description": "Mobile app for field operations",
        "repository_url": "https://github.com/retail-one/nova",
        "slack_channel": "#nova",
        "client_slug": "retail-one",
        "vendor_slug": "hexadev",
        "engagement_name": "Retail One x HexaDev Mobile Delivery Squad",
        "developer_usernames": ["grace", "hector", "iris"],
    },
]

DEVELOPERS = [
    {
        "name": "Alice Chen",
        "email": "alice@hexadev.fr",
        "username": "alice",
        "team": "Frontend",
        "role": "developer",
        "github_username": "alice-chen",
        "company_slug": "hexadev",
        "create_user_account": True,
    },
    {
        "name": "Bob Martinez",
        "email": "bob@hexadev.fr",
        "username": "bob",
        "team": "Backend",
        "role": "developer",
        "github_username": "bob-m",
        "company_slug": "hexadev",
    },
    {
        "name": "Carol Smith",
        "email": "carol@hexadev.fr",
        "username": "carol",
        "team": "Backend",
        "role": "team_lead",
        "github_username": "carol-s",
        "company_slug": "hexadev",
    },
    {
        "name": "David Kim",
        "email": "david@novaforge.fr",
        "username": "david",
        "team": "Frontend",
        "role": "developer",
        "github_username": "dkim",
        "company_slug": "novaforge",
        "create_user_account": True,
    },
    {
        "name": "Eva Rodriguez",
        "email": "eva@novaforge.fr",
        "username": "eva",
        "team": "DevOps",
        "role": "developer",
        "github_username": "eva-r",
        "company_slug": "novaforge",
    },
    {
        "name": "Frank Lee",
        "email": "frank@novaforge.fr",
        "username": "frank",
        "team": "QA",
        "role": "developer",
        "github_username": "frank-l",
        "company_slug": "novaforge",
    },
    {
        "name": "Grace Park",
        "email": "grace@hexadev.fr",
        "username": "grace",
        "team": "Backend",
        "role": "developer",
        "github_username": "grace-p",
        "company_slug": "hexadev",
        "create_user_account": True,
    },
    {
        "name": "Hector Díaz",
        "email": "hector@hexadev.fr",
        "username": "hector",
        "team": "Frontend",
        "role": "developer",
        "github_username": "h-diaz",
        "company_slug": "hexadev",
    },
    {
        "name": "Iris Johnson",
        "email": "iris@hexadev.fr",
        "username": "iris",
        "team": "Backend",
        "role": "team_lead",
        "github_username": "iris-j",
        "company_slug": "hexadev",
    },
]

TENANT_USERS = [
    {
        "username": "horizon_admin",
        "email": "horizon.admin@banque-horizon.fr",
        "role": "client_admin",
        "company_slug": "banque-horizon",
    },
    {
        "username": "horizon_exec",
        "email": "horizon.exec@banque-horizon.fr",
        "role": "client_exec",
        "company_slug": "banque-horizon",
    },
    {
        "username": "retail_pm",
        "email": "retail.pm@retail-one.fr",
        "role": "client_pm",
        "company_slug": "retail-one",
    },
    {
        "username": "hexadev_admin",
        "email": "admin@hexadev.fr",
        "role": "esn_admin",
        "company_slug": "hexadev",
    },
    {
        "username": "novaforge_delivery",
        "email": "delivery@novaforge.fr",
        "role": "esn_delivery_manager",
        "company_slug": "novaforge",
    },
]

TICKET_TEMPLATES = [
    {"title": "Implement user authentication flow",       "ticket_type": "story", "priority": "high",     "story_points": 8,  "estimated_hours": 16},
    {"title": "Fix null pointer in PaymentService",       "ticket_type": "bug",   "priority": "critical", "story_points": 3,  "estimated_hours": 4},
    {"title": "Add Redis caching to product catalog API", "ticket_type": "task",  "priority": "medium",   "story_points": 5,  "estimated_hours": 8},
    {"title": "Write unit tests for OrderController",     "ticket_type": "task",  "priority": "medium",   "story_points": 3,  "estimated_hours": 6},
    {"title": "Upgrade PostgreSQL to v16",                "ticket_type": "task",  "priority": "high",     "story_points": 5,  "estimated_hours": 10},
    {"title": "Design new onboarding wizard UI",         "ticket_type": "story", "priority": "medium",   "story_points": 8,  "estimated_hours": 20},
    {"title": "Database query optimisation — reports",   "ticket_type": "task",  "priority": "high",     "story_points": 5,  "estimated_hours": 8},
    {"title": "Add pagination to /api/v1/tickets",       "ticket_type": "task",  "priority": "low",      "story_points": 2,  "estimated_hours": 3},
    {"title": "Integrate Stripe v4 SDK",                 "ticket_type": "story", "priority": "critical", "story_points": 13, "estimated_hours": 24},
    {"title": "Resolve CORS issue on staging",           "ticket_type": "bug",   "priority": "high",     "story_points": 2,  "estimated_hours": 2},
    {"title": "Implement CSV export for analytics",      "ticket_type": "story", "priority": "medium",   "story_points": 5,  "estimated_hours": 10},
    {"title": "Set up CI/CD pipeline for mobile",        "ticket_type": "task",  "priority": "high",     "story_points": 8,  "estimated_hours": 16},
]

STATUSES_ACTIVE = ["todo", "in_progress", "in_review", "blocked"]
STATUSES_DONE = ["done"] * 6 + ["in_progress", "in_review", "todo", "blocked"]


async def seed(session: AsyncSession) -> None:
    print("🌱 Seeding SprintPulse demo data...")

    from sqlalchemy import select
    existing_seed_project = await session.scalar(
        select(Project.id).where(Project.key.in_([p["key"] for p in PROJECTS])).limit(1)
    )
    if existing_seed_project is not None:
        print("  ✓ Demo project seed already present — skipping duplicate inserts")
        await session.commit()
        return

    company_map: dict[str, Company] = {}
    for company_data in COMPANIES:
        company = Company(**company_data, is_active=True)
        session.add(company)
        await session.flush()
        company_map[company.slug] = company
    print(f"  ✓ {len(company_map)} tenant companies created")

    e2e_user = User(
        username="e2e",
        email="e2e@sprintpulse.test",
        password_hash=hash_password("E2ePassword1!"),
        role="client_admin",
        company_id=company_map["banque-horizon"].id,
        is_active=True,
        is_superuser=True,
    )
    session.add(e2e_user)

    for user_data in TENANT_USERS:
        session.add(
            User(
                username=user_data["username"],
                email=user_data["email"],
                password_hash=hash_password("ChangeMe123!"),
                role=user_data["role"],
                company_id=company_map[user_data["company_slug"]].id,
                is_active=True,
                is_superuser=False,
            )
        )
    await session.flush()
    print("  ✓ tenant admin, manager, and executive accounts created")

    # ── Developers ──────────────────────────────────────────────────────────
    devs: list[Developer] = []
    developer_by_username: dict[str, Developer] = {}
    for d in DEVELOPERS:
        payload = {
            "name": d["name"],
            "email": d["email"],
            "username": d["username"],
            "team": d["team"],
            "role": d["role"],
            "github_username": d["github_username"],
            "company_id": company_map[d["company_slug"]].id,
        }
        dev = Developer(**payload)
        session.add(dev)
        devs.append(dev)
        developer_by_username[d["username"]] = dev
    await session.flush()
    print(f"  ✓ {len(devs)} developers created")

    for d in DEVELOPERS:
        if not d.get("create_user_account"):
            continue
        developer = developer_by_username[d["username"]]
        session.add(
            User(
                username=f"{developer.username}_account",
                email=f"{developer.username}.account@{d['company_slug']}.demo",
                password_hash=hash_password("Developer123!"),
                role="developer",
                company_id=developer.company_id,
                developer_id=developer.id,
                is_active=True,
                is_superuser=False,
            )
        )
    await session.flush()
    print("  ✓ developer user accounts created")

    # ── Projects + Sprints + Tickets ────────────────────────────────────────
    today = date.today()
    all_tickets: list[Ticket] = []
    trello_card_count = 0
    trello_action_count = 0

    for idx, proj_data in enumerate(PROJECTS):
        project = Project(
            name=proj_data["name"],
            key=proj_data["key"],
            description=proj_data["description"],
            repository_url=proj_data["repository_url"],
            slack_channel=proj_data["slack_channel"],
        )
        session.add(project)
        await session.flush()

        project_devs = [developer_by_username[username] for username in proj_data["developer_usernames"]]
        project_tickets: list[Ticket] = []
        client_company = company_map[proj_data["client_slug"]]
        vendor_company = company_map[proj_data["vendor_slug"]]

        session.add(CompanyProjectAccess(company_id=client_company.id, project_id=project.id))
        session.add(CompanyProjectAccess(company_id=vendor_company.id, project_id=project.id))
        await session.flush()

        engagement = Engagement(
            name=proj_data["engagement_name"],
            status="active",
            client_company_id=client_company.id,
            vendor_company_id=vendor_company.id,
            project_id=project.id,
            description=f"{client_company.name} delivery engagement staffed by {vendor_company.name}.",
            starts_on=today - timedelta(days=45),
            ends_on=today + timedelta(days=120),
            sla_response_hours=8 if idx < 2 else 12,
            client_visible=True,
        )
        session.add(engagement)
        await session.flush()

        for dev_idx, developer in enumerate(project_devs):
            session.add(
                DeveloperAssignment(
                    developer_id=developer.id,
                    engagement_id=engagement.id,
                    assignment_role="team_lead" if developer.role == "team_lead" else "developer",
                    status="active",
                    allocation_percentage=100 if dev_idx == 0 else 80,
                    start_date=today - timedelta(days=30 + dev_idx * 3),
                    end_date=None,
                    is_primary=True,
                )
            )
        await session.flush()

        # Completed sprint (ended 2 weeks ago)
        sprint1_end = today - timedelta(days=14)
        sprint1_start = sprint1_end - timedelta(days=14)
        sprint1 = Sprint(
            project_id=project.id,
            name=f"{project.key}-S1: Foundation",
            goal="Establish core infrastructure and baseline features",
            start_date=sprint1_start,
            end_date=sprint1_end,
            status="completed",
            committed_points=40,
            completed_points=rng.randint(32, 40),
            velocity=rng.uniform(32, 40),
        )
        session.add(sprint1)
        await session.flush()

        # Active sprint (started 1 week ago, ends in 1 week)
        sprint2_start = today - timedelta(days=7)
        sprint2_end = today + timedelta(days=7)
        sprint2 = Sprint(
            project_id=project.id,
            name=f"{project.key}-S2: Acceleration",
            goal="Deliver core user-facing features and close all P1 bugs",
            start_date=sprint2_start,
            end_date=sprint2_end,
            status="active",
            committed_points=45,
            completed_points=0,
        )
        session.add(sprint2)
        await session.flush()

        # Tickets for completed sprint (mostly done)
        for i, tmpl in enumerate(TICKET_TEMPLATES[:10]):
            status = rng.choice(STATUSES_DONE)
            assignee = rng.choice(project_devs)
            actual_h = tmpl["estimated_hours"] * rng.uniform(0.7, 1.5)
            t = Ticket(
                project_id=project.id,
                sprint_id=sprint1.id,
                assignee_id=assignee.id,
                reporter_id=rng.choice(project_devs).id,
                title=f"[{project.key}] {tmpl['title']}",
                description=f"Acceptance criteria: complete {tmpl['title'].lower()} with full test coverage and documentation.",
                status=status,
                priority=tmpl["priority"],
                ticket_type=tmpl["ticket_type"],
                estimated_hours=tmpl["estimated_hours"],
                actual_hours=actual_h if status == "done" else None,
                story_points=tmpl["story_points"],
                last_activity_at=datetime.now(UTC) - timedelta(days=rng.randint(1, 14)),
            )
            session.add(t)
            all_tickets.append(t)
            project_tickets.append(t)

        # Tickets for active sprint (mixed statuses including stalled)
        for i, tmpl in enumerate(TICKET_TEMPLATES):
            if i < 6:
                status = rng.choice(["todo", "in_progress", "in_review"])
            elif i < 9:
                status = "in_progress"
                # Some tickets are stalled (last activity 36-80h ago)
                last_act = datetime.now(UTC) - timedelta(hours=rng.randint(36, 80))
            else:
                status = rng.choice(["backlog", "todo"])
            assignee = rng.choice(project_devs) if status != "backlog" else None
            last_activity = (
                datetime.now(UTC) - timedelta(hours=rng.randint(36, 80))
                if status == "in_progress" and i >= 6
                else datetime.now(UTC) - timedelta(hours=rng.randint(1, 12))
            )
            t = Ticket(
                project_id=project.id,
                sprint_id=sprint2.id,
                assignee_id=assignee.id if assignee else None,
                reporter_id=rng.choice(project_devs).id,
                title=f"[{project.key}] {tmpl['title']}",
                description=f"Acceptance criteria: complete {tmpl['title'].lower()} with full test coverage." if i % 3 != 0 else None,
                status=status,
                priority=tmpl["priority"],
                ticket_type=tmpl["ticket_type"],
                estimated_hours=tmpl["estimated_hours"],
                story_points=tmpl["story_points"],
                last_activity_at=last_activity,
            )
            session.add(t)
            all_tickets.append(t)
            project_tickets.append(t)

        print(
            f"  ✓ Project '{project.name}': engagement + 2 sprints + {10 + len(TICKET_TEMPLATES)} tickets"
        )

        # ── Trello mirror data for developer/client-progress dashboards ─────
        credential = TrelloCredential(
            project_id=project.id,
            api_key=f"{project.key.lower()}-api-key",
            api_token=f"{project.key.lower()}-api-token",
            is_active=True,
        )
        session.add(credential)
        await session.flush()

        board = TrelloBoard(
            credential_id=credential.id,
            trello_id=f"board_{project.key.lower()}",
            name=f"{project.name} Delivery Board",
            description=f"Trello mirror for {project.name}",
            short_url=f"https://trello.example/{project.key.lower()}",
            trello_org_id=f"org_{project.key.lower()}",
            is_closed=False,
            last_synced_at=datetime.now(UTC),
        )
        session.add(board)
        await session.flush()

        backlog_list = TrelloList(
            board_id=board.id,
            trello_id=f"list_{project.key.lower()}_backlog",
            name="Backlog",
            pos=1.0,
            list_type=ListType.BACKLOG,
            is_closed=False,
        )
        wip_list = TrelloList(
            board_id=board.id,
            trello_id=f"list_{project.key.lower()}_wip",
            name="In Progress",
            pos=2.0,
            list_type=ListType.WIP,
            is_closed=False,
        )
        done_list = TrelloList(
            board_id=board.id,
            trello_id=f"list_{project.key.lower()}_done",
            name="Done",
            pos=3.0,
            list_type=ListType.DONE,
            is_closed=False,
        )
        session.add_all([backlog_list, wip_list, done_list])
        await session.flush()

        member_ids = {
            dev.id: f"member_{project.key.lower()}_{dev.username}"
            for dev in project_devs
        }

        mirrored_tickets = sorted(
            project_tickets,
            key=lambda ticket: (
                0 if ticket.status in ("done", "in_progress", "in_review", "blocked") else 1,
                ticket.id,
            ),
        )[:12]

        for card_idx, ticket in enumerate(mirrored_tickets, start=1):
            if ticket.status == "done":
                target_list = done_list
            elif ticket.status in ("in_progress", "in_review", "blocked"):
                target_list = wip_list
            else:
                target_list = backlog_list

            assignee_member_id = (
                member_ids.get(ticket.assignee_id) if ticket.assignee_id is not None else None
            )
            last_activity = ticket.last_activity_at
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=UTC)

            entered_wip_at = (
                last_activity - timedelta(days=rng.randint(1, 4))
                if target_list.list_type in (ListType.WIP, ListType.DONE)
                else None
            )
            entered_done_at = (
                last_activity - timedelta(hours=rng.randint(1, 8))
                if target_list.list_type == ListType.DONE
                else None
            )
            cycle_time_hours = None
            if target_list.list_type == ListType.DONE and entered_wip_at and entered_done_at:
                cycle_time_hours = round(
                    (entered_done_at - entered_wip_at).total_seconds() / 3600, 2
                )

            stalled = (
                target_list.list_type == ListType.WIP
                and (datetime.now(UTC) - last_activity).total_seconds() / 3600 >= 24
            )

            labels = [
                {
                    "id": f"lbl_type_{ticket.id}",
                    "name": ticket.ticket_type,
                    "color": "blue",
                },
                {
                    "id": f"lbl_points_{ticket.id}",
                    "name": f"{ticket.story_points or 1}sp",
                    "color": "green",
                },
            ]
            if ticket.priority == "critical":
                labels.append({
                    "id": f"lbl_priority_{ticket.id}",
                    "name": "bug",
                    "color": "red",
                })

            card = TrelloCard(
                board_id=board.id,
                list_id=target_list.id,
                trello_id=f"card_{project.key.lower()}_{ticket.id}",
                trello_short_id=card_idx,
                name=ticket.title,
                description=ticket.description,
                member_ids=[assignee_member_id] if assignee_member_id else [],
                labels=labels,
                due_date=None,
                due_complete=target_list.list_type == ListType.DONE,
                is_closed=False,
                trello_last_activity=last_activity,
                entered_wip_at=entered_wip_at,
                entered_done_at=entered_done_at,
                trello_created_at=last_activity - timedelta(days=rng.randint(4, 10)),
                cycle_time_hours=cycle_time_hours,
                lead_time_hours=(
                    round(cycle_time_hours + rng.uniform(6, 24), 2)
                    if cycle_time_hours is not None
                    else None
                ),
                is_stalled=stalled,
                stalled_since=last_activity if stalled else None,
            )
            session.add(card)
            await session.flush()
            trello_card_count += 1

            if assignee_member_id:
                assignee = next(dev for dev in project_devs if dev.id == ticket.assignee_id)
                action_time = (card.trello_created_at or last_activity) + timedelta(hours=1)
                session.add(
                    TrelloAction(
                        card_id=card.id,
                        trello_action_id=f"action_assign_{project.key.lower()}_{ticket.id}",
                        action_type="addMemberToCard",
                        action_date=action_time,
                        data={"member_id": assignee_member_id},
                        trello_member_id=assignee_member_id,
                        member_name=assignee.name,
                    )
                )
                trello_action_count += 1

                if target_list.list_type == ListType.WIP:
                    session.add(
                        TrelloAction(
                            card_id=card.id,
                            trello_action_id=f"action_comment_{project.key.lower()}_{ticket.id}",
                            action_type="commentCard",
                            action_date=last_activity - timedelta(hours=4),
                            data={"text": "Any update on this item?"},
                            trello_member_id=assignee_member_id,
                            member_name=assignee.name,
                        )
                    )
                    trello_action_count += 1

                    if not stalled:
                        reviewer = next(
                            dev for dev in project_devs if dev.id != assignee.id
                        )
                        reviewer_member_id = member_ids[reviewer.id]
                        session.add(
                            TrelloAction(
                                card_id=card.id,
                                trello_action_id=f"action_reply_{project.key.lower()}_{ticket.id}",
                                action_type="commentCard",
                                action_date=last_activity - timedelta(hours=2),
                                data={"text": "Progress is moving and review is scheduled."},
                                trello_member_id=reviewer_member_id,
                                member_name=reviewer.name,
                            )
                        )
                        trello_action_count += 1

        print(f"  ✓ Trello mirror for '{project.name}': 1 board + {len(mirrored_tickets)} cards")

    await session.flush()

    # ── Blockers on stalled tickets ─────────────────────────────────────────
    blocker_count = 0
    for ticket in all_tickets:
        last = ticket.last_activity_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        idle_hours = (datetime.now(UTC) - last).total_seconds() / 3600

        if idle_hours >= 24 and ticket.status in ("in_progress", "in_review", "blocked"):
            level = 3 if idle_hours >= 72 else (2 if idle_hours >= 48 else 1)
            blocker = Blocker(
                ticket_id=ticket.id,
                stall_hours=round(idle_hours, 1),
                escalation_level=level,
                detected_at=datetime.now(UTC) - timedelta(hours=idle_hours - 2),
                description=f"Ticket stalled for {idle_hours:.0f}h with no activity.",
            )
            session.add(blocker)
            blocker_count += 1

    await session.flush()
    print(f"  ✓ {blocker_count} blockers created")

    # ── Repository activity records ─────────────────────────────────────────
    repo_count = 0
    for ticket in all_tickets:
        if ticket.status in ("in_progress", "in_review", "done"):
            commit_count = rng.randint(0, 15)
            pr_count = rng.randint(0, 2)
            pr_merged = ticket.status == "done" and rng.random() > 0.1
            last_commit_at = (
                datetime.now(UTC) - timedelta(hours=rng.randint(1, 72))
                if commit_count > 0
                else None
            )

            # Mismatch: in_progress with 0 commits
            mismatch = (ticket.status == "in_progress" and commit_count == 0)
            mismatch_type = "no_commits_in_progress" if mismatch else None
            mismatch_reason = (
                "Ticket is in-progress but has no commits associated with it."
                if mismatch
                else None
            )

            ra = RepositoryActivity(
                ticket_id=ticket.id,
                project_id=ticket.project_id,
                branch_name=f"feature/{ticket.id}-{ticket.title[5:25].lower().replace(' ', '-').replace('[', '').replace(']', '')}",
                commit_count=commit_count,
                pr_count=pr_count,
                pr_merged=pr_merged,
                last_commit_at=last_commit_at,
                mismatch_detected=mismatch,
                mismatch_type=mismatch_type,
                mismatch_reason=mismatch_reason,
                scanned_at=datetime.now(UTC),
            )
            session.add(ra)
            repo_count += 1

    await session.flush()
    print(f"  ✓ {repo_count} repository activity records created")
    print(f"  ✓ {trello_card_count} Trello cards + {trello_action_count} Trello actions created")

    # ── KPI snapshots ────────────────────────────────────────────────────────
    for project in await _get_all_projects(session):
        for sprint_status, velocity in [("completed", rng.uniform(32, 40)), ("active", rng.uniform(10, 25))]:
            snapshot = KPISnapshot(
                project_id=project.id,
                sprint_id=None,
                cycle_time_hours=round(rng.uniform(20, 60), 2),
                lead_time_hours=round(rng.uniform(40, 120), 2),
                velocity=round(velocity, 2),
                completion_rate=round(rng.uniform(0.7, 1.0), 4),
                estimation_accuracy=round(rng.uniform(0.65, 0.95), 4),
                throughput=round(rng.uniform(0.5, 2.0), 4),
                bug_rate=round(rng.uniform(0.1, 0.3), 4),
                computed_at=datetime.now(UTC),
            )
            session.add(snapshot)

    await session.flush()
    print("  ✓ KPI snapshots created")

    await session.commit()
    print("\n✅ Seed complete!")
    print(f"   Companies: {len(COMPANIES)}")
    print(f"   Projects: {len(PROJECTS)}")
    print(f"   Developers: {len(DEVELOPERS)}")
    print(f"   Tickets: {len(all_tickets)}")
    print(f"   Blockers: {blocker_count}")


async def _get_all_projects(session: AsyncSession) -> list[Project]:
    from sqlalchemy import select
    result = await session.execute(select(Project))
    return list(result.scalars().all())


async def main() -> None:
    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables ready.\n")

    async with AsyncSessionLocal() as session:
        await seed(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
