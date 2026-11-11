import asyncio
import os
import sys
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

# Append backend directory so `app` can be resolved
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.company import Company, CompanyProjectAccess
from app.models.user import User
from app.models.developer import Developer
from app.models.engagement import DeveloperAssignment, Engagement
from app.models.project import Project
from app.models.sprint import Sprint
from app.models.ticket import Ticket
from app.core.security import hash_password
from app.database import engine


async def get_or_create_company(session: AsyncSession, *, name: str, slug: str, tenant_type: str) -> Company:
    company = await session.scalar(select(Company).where(Company.slug == slug))
    if company:
        company.name = name
        company.tenant_type = tenant_type
        return company

    company = Company(name=name, slug=slug, tenant_type=tenant_type)
    session.add(company)
    await session.flush()
    return company


async def get_or_create_user(
    session: AsyncSession,
    *,
    username: str,
    email: str,
    role: str,
    company_id: int,
    developer_id: int | None = None,
) -> User:
    user = await session.scalar(select(User).where(User.username == username))
    password_hash = hash_password("Password123!")
    if user:
        user.email = email
        user.password_hash = password_hash
        user.role = role
        user.company_id = company_id
        user.developer_id = developer_id
        user.is_active = True
        return user

    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        role=role,
        company_id=company_id,
        developer_id=developer_id,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def get_or_create_engagement(
    session: AsyncSession,
    *,
    name: str,
    client_company_id: int,
    vendor_company_id: int,
    project_id: int,
) -> Engagement:
    engagement = await session.scalar(
        select(Engagement).where(
            Engagement.client_company_id == client_company_id,
            Engagement.vendor_company_id == vendor_company_id,
            Engagement.project_id == project_id,
        )
    )
    if engagement:
        engagement.name = name
        engagement.status = "active"
        engagement.client_visible = True
        return engagement

    engagement = Engagement(
        name=name,
        client_company_id=client_company_id,
        vendor_company_id=vendor_company_id,
        project_id=project_id,
        status="active",
        client_visible=True,
    )
    session.add(engagement)
    await session.flush()
    return engagement


async def get_or_create_assignment(
    session: AsyncSession,
    *,
    developer_id: int,
    engagement_id: int,
    start_date: date,
) -> DeveloperAssignment:
    assignment = await session.scalar(
        select(DeveloperAssignment).where(
            DeveloperAssignment.developer_id == developer_id,
            DeveloperAssignment.engagement_id == engagement_id,
        )
    )
    if assignment:
        assignment.status = "active"
        assignment.assignment_role = "Backend Developer"
        assignment.allocation_percentage = 100
        assignment.is_primary = True
        return assignment

    assignment = DeveloperAssignment(
        developer_id=developer_id,
        engagement_id=engagement_id,
        assignment_role="Backend Developer",
        status="active",
        allocation_percentage=100,
        start_date=start_date,
        is_primary=True,
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def seed():
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        norma = await get_or_create_company(session, name="Norma", slug="norma", tenant_type="client")
        tawssil = await get_or_create_company(session, name="Tawssil", slug="tawssil", tenant_type="vendor")

        await get_or_create_user(
            session,
            username="norma_admin",
            email="admin@norma.com",
            role="client_admin",
            company_id=norma.id,
        )

        await get_or_create_user(
            session,
            username="tawssil_admin",
            email="admin@tawssil.com",
            role="esn_admin",
            company_id=tawssil.id,
        )

        hejer = await session.scalar(select(Developer).where(Developer.username == "hejer"))
        if hejer:
            hejer.name = "Hejer Bettita"
            hejer.email = "hejer@tawssil.com"
            hejer.role = "engineer"
            hejer.company_id = tawssil.id
        else:
            hejer = Developer(
                name="Hejer Bettita",
                email="hejer@tawssil.com",
                username="hejer",
                role="engineer",
                company_id=tawssil.id,
            )
            session.add(hejer)
            await session.flush()

        await get_or_create_user(
            session,
            username="hejer_dev",
            email="hejer@tawssil.com",
            role="developer",
            company_id=tawssil.id,
            developer_id=hejer.id,
        )

        project = await session.scalar(select(Project).where(Project.key == "NORM"))
        if project:
            project.name = "Norma Base Project"
            project.description = "Development of Norma by Tawssil developers"
        else:
            project = Project(
                name="Norma Base Project",
                key="NORM",
                description="Development of Norma by Tawssil developers",
            )
            session.add(project)
            await session.flush()

        for company in (norma, tawssil):
            access = await session.scalar(
                select(CompanyProjectAccess).where(
                    CompanyProjectAccess.company_id == company.id,
                    CompanyProjectAccess.project_id == project.id,
                )
            )
            if not access:
                session.add(CompanyProjectAccess(company_id=company.id, project_id=project.id))

        today = date.today()
        engagement = await get_or_create_engagement(
            session,
            name="Norma x Tawssil Delivery",
            client_company_id=norma.id,
            vendor_company_id=tawssil.id,
            project_id=project.id,
        )
        await get_or_create_assignment(
            session,
            developer_id=hejer.id,
            engagement_id=engagement.id,
            start_date=today,
        )

        sprint = await session.scalar(
            select(Sprint).where(
                Sprint.project_id == project.id,
                Sprint.name == "Sprint 1 - Foundation",
            )
        )
        if sprint:
            sprint.status = "active"
            sprint.start_date = today
            sprint.end_date = today + timedelta(days=14)
        else:
            sprint = Sprint(
                project_id=project.id,
                name="Sprint 1 - Foundation",
                status="active",
                start_date=today,
                end_date=today + timedelta(days=14),
            )
            session.add(sprint)
            await session.flush()

        ticket = await session.scalar(
            select(Ticket).where(
                Ticket.project_id == project.id,
                Ticket.title == "Setup core endpoints for Norma APP",
            )
        )
        if ticket:
            ticket.sprint_id = sprint.id
            ticket.assignee_id = hejer.id
            ticket.status = "in_progress"
            ticket.priority = "high"
            ticket.ticket_type = "feature"
        else:
            session.add(
                Ticket(
                    project_id=project.id,
                    sprint_id=sprint.id,
                    assignee_id=hejer.id,
                    title="Setup core endpoints for Norma APP",
                    status="in_progress",
                    priority="high",
                    ticket_type="feature",
                )
            )

        await session.commit()
        print("Data ready for Norma <> Tawssil flow.")

if __name__ == "__main__":
    asyncio.run(seed())
