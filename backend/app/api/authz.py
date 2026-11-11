from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import DbSession
from app.config import settings
from app.models.company import Company, CompanyProjectAccess
from app.models.developer import Developer
from app.models.developer_external_identity import DeveloperExternalIdentity
from app.models.engagement import DeveloperAssignment, Engagement
from app.models.project import Project
from app.models.user import User

AppRole = Literal[
    "super_admin",
    "company_admin",
    "company_manager",
    "client_admin",
    "client_exec",
    "client_pm",
    "esn_admin",
    "esn_delivery_manager",
    "developer",
    "auditor_readonly",
]


@dataclass(slots=True)
class AuthPrincipal:
    user_id: int
    username: str
    email: str
    role: AppRole
    company_id: int | None
    company_slug: str | None = None
    developer_id: int | None = None
    is_active: bool = True

    @property
    def is_solution_owner(self) -> bool:
        return self.company_slug == "norma"

    @property
    def is_superuser(self) -> bool:
        return self.role == "super_admin"

    @property
    def is_company_user(self) -> bool:
        return self.role in {
            "company_admin",
            "company_manager",
            "client_admin",
            "client_exec",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
            "auditor_readonly",
        }

    @property
    def is_client_user(self) -> bool:
        return self.role in {"company_admin", "company_manager", "client_admin", "client_exec", "client_pm"}

    @property
    def is_vendor_user(self) -> bool:
        return self.role in {"esn_admin", "esn_delivery_manager"}


def _principal_from_user(user: User) -> AuthPrincipal:
    role: AppRole = "super_admin" if user.is_superuser else user.role  # type: ignore[assignment]
    return AuthPrincipal(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=role,
        company_id=user.company_id,
        company_slug=user.company.slug if user.company else None,
        developer_id=user.developer_id,
        is_active=user.is_active,
    )


def member_numeric_id(member_id: str | None) -> int | None:
    if not member_id:
        return None
    return int(hashlib.sha1(str(member_id).encode()).hexdigest()[:8], 16)


async def get_current_principal(request: Request, session: DbSession) -> AuthPrincipal:
    if not settings.auth_enabled:
        return AuthPrincipal(
            user_id=0,
            username="system",
            email="system@kpimaster.local",
            role="super_admin",
            company_id=None,
            company_slug=None,
            developer_id=None,
            is_active=True,
        )

    user_id = getattr(request.state, "auth_user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    from sqlalchemy.orm import joinedload
    user = await session.scalar(
        select(User).options(joinedload(User.company)).where(User.id == int(user_id))
    )
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid user.")
    return _principal_from_user(user)


CurrentPrincipal = Annotated[AuthPrincipal, Depends(get_current_principal)]


def require_roles(*roles: AppRole):
    async def _require(principal: CurrentPrincipal) -> AuthPrincipal:
        if principal.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
        return principal

    return _require


async def ensure_project_access(
    session: DbSession,
    principal: AuthPrincipal,
    project_id: int,
) -> None:
    if principal.is_superuser or principal.is_solution_owner:
        return

    if principal.company_id is None:
        raise HTTPException(status_code=403, detail="No company is associated with this account.")

    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    company = await session.get(Company, principal.company_id)
    if company and company.tenant_type == "vendor":
        link_count = await session.scalar(
            select(func.count())
            .select_from(Engagement)
            .where(
                Engagement.vendor_company_id == principal.company_id,
                Engagement.project_id == project_id,
            )
        )
    else:
        link_count = await session.scalar(
            select(func.count())
            .select_from(CompanyProjectAccess)
            .where(
                CompanyProjectAccess.company_id == principal.company_id,
                CompanyProjectAccess.project_id == project_id,
            )
        )
    if not link_count:
        raise HTTPException(status_code=403, detail="This project is not visible to your company.")


async def ensure_developer_access(
    session: DbSession, principal: AuthPrincipal, developer_id: int
) -> Developer:
    if principal.is_superuser or principal.is_solution_owner:
        developer = await session.get(Developer, developer_id)
        if not developer:
            raise HTTPException(status_code=404, detail="Developer not found.")
        return developer

    if principal.company_id is None:
        raise HTTPException(status_code=403, detail="This developer is not managed by your company.")

    developer = await session.get(Developer, developer_id)
    if developer is None:
        raise HTTPException(status_code=404, detail="Developer not found.")

    if principal.role == "developer":
        if principal.developer_id != developer_id:
            raise HTTPException(status_code=403, detail="Developers can only access their own KPI data.")
        return developer

    company = await session.get(Company, principal.company_id)
    if company and company.tenant_type == "vendor":
        if developer.company_id == principal.company_id:
            return developer
        raise HTTPException(status_code=403, detail="This developer is not managed by your company.")

    if developer.company_id == principal.company_id:
        return developer

    assignment_count = await session.scalar(
        select(func.count())
        .select_from(DeveloperAssignment)
        .join(Engagement, Engagement.id == DeveloperAssignment.engagement_id)
        .outerjoin(CompanyProjectAccess, CompanyProjectAccess.project_id == Engagement.project_id)
        .where(
            DeveloperAssignment.developer_id == developer.id,
            or_(
                Engagement.client_company_id == principal.company_id,
                Engagement.vendor_company_id == principal.company_id,
                CompanyProjectAccess.company_id == principal.company_id,
            ),
        )
    )
    if not assignment_count:
        raise HTTPException(status_code=403, detail="This developer is not managed by your company.")
    return developer


async def get_allowed_kpi_subject_ids(
    session: AsyncSession,
    principal: AuthPrincipal,
    project_id: int | None = None,
) -> set[int] | None:
    if principal.is_superuser or principal.is_solution_owner:
        return None

    if principal.role == "developer":
        if principal.developer_id is None:
            return set()
        developer = await session.get(Developer, principal.developer_id)
        if developer is None:
            return set()
        ids: set[int] = {developer.id}
        trello_id = member_numeric_id(developer.trello_member_id)
        if trello_id is not None:
            ids.add(trello_id)
        identity_rows = await session.execute(
            select(DeveloperExternalIdentity.external_user_id)
            .where(
                DeveloperExternalIdentity.developer_id == developer.id,
                DeveloperExternalIdentity.is_active.is_(True),
            )
        )
        for (external_user_id,) in identity_rows.all():
            external_numeric_id = member_numeric_id(external_user_id)
            if external_numeric_id is not None:
                ids.add(external_numeric_id)
        return ids

    stmt = (
        select(Developer.id, Developer.trello_member_id)
        .distinct()
        .join(DeveloperAssignment, DeveloperAssignment.developer_id == Developer.id)
        .join(Engagement, Engagement.id == DeveloperAssignment.engagement_id)
        .where(
            DeveloperAssignment.status == "active",
            Engagement.status == "active"
        )
    )

    if project_id is not None:
        stmt = stmt.where(Engagement.project_id == project_id)

    # Apply company scoping if not a superuser/owner
    if not (principal.is_superuser or principal.is_solution_owner):
        if principal.company_id is None:
            return set()
        
        company = await session.get(Company, principal.company_id)
        if company and company.tenant_type == "vendor":
            # Vendors see their own developers assigned to the engagements
            stmt = stmt.where(Developer.company_id == principal.company_id)
        else:
            # Clients see developers assigned to engagements where they are the client
            stmt = stmt.where(Engagement.client_company_id == principal.company_id)

    result = await session.execute(stmt)
    # Plus internal developers if the user is client/vendor looking at their OWN staff (optional fallback)
    # However, the user specifically requested ONLY "the developer that has been attached to the affected outsourcing company"
    # So we strictly stick to the outsourced Engagement mapping above.
    return await _expand_developer_subject_ids(session, result.all())


async def _expand_developer_subject_ids(
    session: AsyncSession,
    developer_rows: list[tuple[int, str | None]],
) -> set[int]:
    ids: set[int] = set()
    developer_ids = [developer_id for developer_id, _ in developer_rows]
    for developer_id, trello_member_id in developer_rows:
        ids.add(developer_id)
        trello_id = member_numeric_id(trello_member_id)
        if trello_id is not None:
            ids.add(trello_id)
    if not developer_ids:
        return ids

    identity_rows = await session.execute(
        select(DeveloperExternalIdentity.developer_id, DeveloperExternalIdentity.external_user_id)
        .where(
            DeveloperExternalIdentity.developer_id.in_(developer_ids),
            DeveloperExternalIdentity.is_active.is_(True),
        )
    )
    for developer_id, external_user_id in identity_rows.all():
        ids.add(developer_id)
        external_numeric_id = member_numeric_id(external_user_id)
        if external_numeric_id is not None:
            ids.add(external_numeric_id)
    return ids


async def ensure_kpi_subject_access(
    session: AsyncSession,
    principal: AuthPrincipal,
    kpi_subject_id: int,
    project_id: int | None = None,
) -> None:
    allowed_ids = await get_allowed_kpi_subject_ids(session, principal, project_id)
    if allowed_ids is None:
        return
    if not allowed_ids:
        if principal.role == "developer":
            raise HTTPException(status_code=403, detail="This account is not linked to a Trello developer profile.")
        raise HTTPException(status_code=403, detail="No developer KPI records are visible to your company for this project.")
    if kpi_subject_id not in allowed_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this developer KPI record.")


async def list_accessible_project_ids(session: AsyncSession, principal: AuthPrincipal) -> list[int] | None:
    if principal.is_superuser or principal.is_solution_owner:
        return None
    if principal.company_id is None:
        return []

    company = await session.get(Company, principal.company_id)
    if company and company.tenant_type == "vendor":
        rows = await session.execute(
            select(Engagement.project_id)
            .where(Engagement.vendor_company_id == principal.company_id)
            .order_by(Engagement.project_id)
        )
    else:
        rows = await session.execute(
            select(CompanyProjectAccess.project_id)
            .where(CompanyProjectAccess.company_id == principal.company_id)
            .order_by(CompanyProjectAccess.project_id)
        )
    return [row[0] for row in rows.all()]


async def ensure_engagement_access(
    session: DbSession,
    principal: AuthPrincipal,
    engagement_id: int,
) -> Engagement:
    if principal.is_superuser or principal.is_solution_owner:
        engagement = await session.get(Engagement, engagement_id)
        if not engagement:
            raise HTTPException(status_code=404, detail="Engagement not found.")
        return engagement

    if principal.company_id is None:
        raise HTTPException(status_code=403, detail="No company is associated with this account.")
    
    engagement = await session.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found.")
        
    if principal.company_id not in {engagement.client_company_id, engagement.vendor_company_id}:
        raise HTTPException(status_code=403, detail="This engagement is not visible to your company.")
    return engagement
