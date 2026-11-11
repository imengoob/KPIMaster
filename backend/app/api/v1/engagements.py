from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_engagement_access, require_roles
from app.api.dependencies import DbSession
from app.models.company import Company, CompanyProjectAccess
from app.models.developer import Developer
from app.models.engagement import DeveloperAssignment, Engagement
from app.models.project import Project
from app.schemas.engagement import (
    DeveloperAssignmentCreate,
    DeveloperAssignmentResponse,
    EngagementCreate,
    EngagementResponse,
)

router = APIRouter(prefix="/engagements", tags=["Engagements"])


def _engagement_response(engagement: Engagement) -> EngagementResponse:
    return EngagementResponse(
        id=engagement.id,
        name=engagement.name,
        status=engagement.status,
        client_company_id=engagement.client_company_id,
        client_company_name=engagement.client_company.name,
        vendor_company_id=engagement.vendor_company_id,
        vendor_company_name=engagement.vendor_company.name,
        project_id=engagement.project_id,
        project_name=engagement.project.name,
        description=engagement.description,
        starts_on=engagement.starts_on,
        ends_on=engagement.ends_on,
        sla_response_hours=engagement.sla_response_hours,
        client_visible=engagement.client_visible,
        created_at=engagement.created_at,
        updated_at=engagement.updated_at,
    )


def _assignment_response(assignment: DeveloperAssignment) -> DeveloperAssignmentResponse:
    engagement = assignment.engagement
    developer = assignment.developer
    return DeveloperAssignmentResponse(
        id=assignment.id,
        developer_id=assignment.developer_id,
        developer_name=developer.name,
        developer_company_id=developer.company_id,
        engagement_id=assignment.engagement_id,
        project_id=engagement.project_id,
        project_name=engagement.project.name,
        client_company_id=engagement.client_company_id,
        client_company_name=engagement.client_company.name,
        vendor_company_id=engagement.vendor_company_id,
        vendor_company_name=engagement.vendor_company.name,
        assignment_role=assignment.assignment_role,
        status=assignment.status,
        allocation_percentage=assignment.allocation_percentage,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        is_primary=assignment.is_primary,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


async def _ensure_company_type(session: DbSession, company_id: int, expected_type: str) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    if company.tenant_type != expected_type:
        raise HTTPException(
            status_code=422,
            detail=f"Company '{company.name}' is not a {expected_type} tenant.",
        )
    return company


async def _ensure_project_link(session: DbSession, company_id: int, project_id: int) -> None:
    existing = await session.scalar(
        select(CompanyProjectAccess).where(
            CompanyProjectAccess.company_id == company_id,
            CompanyProjectAccess.project_id == project_id,
        )
    )
    if existing is None:
        session.add(CompanyProjectAccess(company_id=company_id, project_id=project_id))


@router.get("", response_model=list[EngagementResponse])
async def list_engagements(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int | None = Query(None),
) -> list[EngagementResponse]:
    stmt = select(Engagement).order_by(Engagement.name)
    if project_id is not None:
        stmt = stmt.where(Engagement.project_id == project_id)
    if not principal.is_superuser:
        if principal.company_id is None:
            return []
        stmt = stmt.where(
            (Engagement.client_company_id == principal.company_id)
            | (Engagement.vendor_company_id == principal.company_id)
        )
    result = await session.execute(stmt)
    engagements = list(result.scalars().all())
    for engagement in engagements:
        await session.refresh(engagement, attribute_names=["client_company", "vendor_company", "project"])
    return [_engagement_response(engagement) for engagement in engagements]


@router.post("", response_model=EngagementResponse, status_code=status.HTTP_201_CREATED)
async def create_engagement(
    body: EngagementCreate,
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles("super_admin", "company_admin", "client_admin", "client_pm")
    ),
) -> EngagementResponse:
    client_company_id = body.client_company_id
    if not principal.is_superuser:
        if principal.company_id is None:
            raise HTTPException(status_code=403, detail="No company is associated with this account.")
        client_company_id = principal.company_id

    if client_company_id is None:
        raise HTTPException(status_code=422, detail="client_company_id is required.")

    client_company = await _ensure_company_type(session, client_company_id, "client")
    vendor_company = await _ensure_company_type(session, body.vendor_company_id, "vendor")
    project = await session.get(Project, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    engagement = Engagement(
        name=body.name,
        status=body.status,
        client_company_id=client_company.id,
        vendor_company_id=vendor_company.id,
        project_id=project.id,
        description=body.description,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        sla_response_hours=body.sla_response_hours,
        client_visible=body.client_visible,
    )
    session.add(engagement)
    await _ensure_project_link(session, client_company.id, project.id)
    await _ensure_project_link(session, vendor_company.id, project.id)
    await session.flush()
    await session.refresh(engagement, attribute_names=["client_company", "vendor_company", "project"])
    return _engagement_response(engagement)


@router.get("/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(
    engagement_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
) -> EngagementResponse:
    engagement = await ensure_engagement_access(session, principal, engagement_id)
    await session.refresh(engagement, attribute_names=["client_company", "vendor_company", "project"])
    return _engagement_response(engagement)


@router.get("/{engagement_id}/assignments", response_model=list[DeveloperAssignmentResponse])
async def list_assignments(
    engagement_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
) -> list[DeveloperAssignmentResponse]:
    engagement = await ensure_engagement_access(session, principal, engagement_id)
    result = await session.execute(
        select(DeveloperAssignment)
        .where(DeveloperAssignment.engagement_id == engagement.id)
        .order_by(DeveloperAssignment.start_date.desc(), DeveloperAssignment.id.desc())
    )
    assignments = list(result.scalars().all())
    for assignment in assignments:
        await session.refresh(
            assignment,
            attribute_names=[
                "developer",
                "engagement",
            ],
        )
        await session.refresh(
            assignment.engagement,
            attribute_names=["project", "client_company", "vendor_company"],
        )
    return [_assignment_response(assignment) for assignment in assignments]


@router.post(
    "/{engagement_id}/assignments",
    response_model=DeveloperAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment(
    engagement_id: int,
    body: DeveloperAssignmentCreate,
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
        )
    ),
) -> DeveloperAssignmentResponse:
    engagement = await ensure_engagement_access(session, principal, engagement_id)
    developer = await session.get(Developer, body.developer_id)
    if developer is None:
        raise HTTPException(status_code=404, detail="Developer not found.")
    if developer.company_id != engagement.vendor_company_id:
        raise HTTPException(
            status_code=422,
            detail="Developers can only be assigned from the vendor company linked to the engagement.",
        )
    assignment = DeveloperAssignment(
        developer_id=developer.id,
        engagement_id=engagement.id,
        assignment_role=body.assignment_role,
        status=body.status,
        allocation_percentage=body.allocation_percentage,
        start_date=body.start_date,
        end_date=body.end_date,
        is_primary=body.is_primary,
    )
    session.add(assignment)
    await session.flush()
    await session.refresh(assignment, attribute_names=["developer", "engagement"])
    await session.refresh(assignment.engagement, attribute_names=["project", "client_company", "vendor_company"])
    return _assignment_response(assignment)
