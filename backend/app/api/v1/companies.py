from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_developer_access, require_roles
from app.api.dependencies import DbSession
from app.core.security import hash_password
from app.models.company import Company, CompanyProjectAccess
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import UserRead
from app.models.user import User
from app.schemas.auth import UserRead
from app.schemas.company import CompanyResponse, CompanyUpdate, CompanyUserCreate, CompanyPartnershipCreate, CompanyPartnershipResponse
from app.schemas.project import ProjectResponse
from app.models.company import Company, CompanyProjectAccess, CompanyPartnership

router = APIRouter(prefix="/companies", tags=["Companies"])


def _to_user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        role="super_admin" if user.is_superuser else user.role,
        company_id=user.company_id,
        company_name=user.company.name if user.company else None,
        company_slug=user.company.slug if user.company else None,
        company_type=user.company.tenant_type if user.company else None,
        developer_id=user.developer_id,
        kpi_subject_id=user.developer_id if user.developer else None,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
    )


async def _load_principal_company(session: DbSession, principal: CurrentPrincipal) -> Company:
    if principal.company_id is None:
        raise HTTPException(status_code=404, detail="No company is linked to this account.")
    company = await session.get(Company, principal.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return company


@router.get("/me", response_model=CompanyResponse)
async def get_my_company(
    session: DbSession,
    principal: CurrentPrincipal,
) -> CompanyResponse:
    company = await _load_principal_company(session, principal)
    return CompanyResponse.model_validate(company)


@router.patch("/me", response_model=CompanyResponse)
async def update_my_company(
    body: CompanyUpdate,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "company_admin", "client_admin", "esn_admin")),
) -> CompanyResponse:
    company = await _load_principal_company(session, principal)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "tenant_type" and not principal.is_superuser:
            continue
        setattr(company, key, value)
    await session.flush()
    await session.refresh(company)
    return CompanyResponse.model_validate(company)


@router.get("/me/users", response_model=list[UserRead])
async def list_my_company_users(
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_exec",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
            "auditor_readonly",
        )
    ),
) -> list[UserRead]:
    company = await _load_principal_company(session, principal)
    result = await session.execute(
        select(User).where(User.company_id == company.id).order_by(User.username)
    )
    return [_to_user_read(user) for user in result.scalars().all()]


@router.post("/me/users", response_model=UserRead, status_code=201)
async def create_company_user(
    body: CompanyUserCreate,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "company_admin", "client_admin", "esn_admin")),
) -> UserRead:
    company = await _load_principal_company(session, principal)
    if body.role not in {
        "company_admin",
        "company_manager",
        "client_admin",
        "client_exec",
        "client_pm",
        "esn_admin",
        "esn_delivery_manager",
        "developer",
        "auditor_readonly",
    }:
        raise HTTPException(status_code=422, detail="Unsupported company user role.")

    existing = await session.scalar(
        select(User).where((User.username == body.username.strip()) | (User.email == body.email.lower().strip()))
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists.")

    developer_id = None
    if body.role == "developer":
        if body.developer_id is None:
            raise HTTPException(status_code=422, detail="developer_id is required for developer accounts.")
        developer = await ensure_developer_access(session, principal, body.developer_id)
        linked_user = await session.scalar(select(User).where(User.developer_id == developer.id))
        if linked_user is not None:
            raise HTTPException(status_code=409, detail="This developer already has an account.")
        developer_id = developer.id

    user = User(
        username=body.username.strip(),
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        role=body.role,
        company_id=company.id,
        developer_id=developer_id,
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user, attribute_names=["company", "developer"])
    return _to_user_read(user)


@router.get("/me/projects", response_model=list[ProjectResponse])
async def list_company_projects(
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_exec",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
            "auditor_readonly",
        )
    ),
) -> list[ProjectResponse]:
    company = await _load_principal_company(session, principal)
    stmt = (
        select(Project)
        .join(CompanyProjectAccess, CompanyProjectAccess.project_id == Project.id)
        .where(CompanyProjectAccess.company_id == company.id)
        .order_by(Project.name)
    )
    result = await session.execute(stmt)
    return [ProjectResponse.model_validate(project) for project in result.scalars().all()]


@router.post("/me/projects/{project_id}", response_model=ProjectResponse, status_code=201)
async def grant_company_project_access(
    project_id: int,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "company_admin", "client_admin", "esn_admin")),
) -> ProjectResponse:
    company = await _load_principal_company(session, principal)
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    existing = await session.scalar(
        select(CompanyProjectAccess).where(
            CompanyProjectAccess.company_id == company.id,
            CompanyProjectAccess.project_id == project_id,
        )
    )
    if existing is None:
        session.add(CompanyProjectAccess(company_id=company.id, project_id=project_id))
        await session.flush()
    return ProjectResponse.model_validate(project)


@router.delete("/me/projects/{project_id}", status_code=204)
async def revoke_company_project_access(
    project_id: int,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "company_admin", "client_admin", "esn_admin")),
) -> None:
    company = await _load_principal_company(session, principal)
    link = await session.scalar(
        select(CompanyProjectAccess).where(
            CompanyProjectAccess.company_id == company.id,
            CompanyProjectAccess.project_id == project_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Project visibility link not found.")
    await session.delete(link)
    await session.flush()


@router.get("", response_model=list[CompanyResponse])
async def list_companies(
    session: DbSession,
    tenant_type: str | None = None,
    principal: AuthPrincipal = Depends(
        require_roles("super_admin", "company_admin", "client_admin", "client_pm")
    ),
) -> list[CompanyResponse]:
    stmt = select(Company).order_by(Company.name)
    if tenant_type:
        stmt = stmt.where(Company.tenant_type == tenant_type)
    result = await session.execute(stmt)
    return [CompanyResponse.model_validate(comp) for comp in result.scalars().all()]


@router.post("/me/partnerships", response_model=CompanyPartnershipResponse, status_code=201)
async def create_partnership(
    body: CompanyPartnershipCreate,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "client_admin", "client_exec", "client_pm")),
) -> CompanyPartnershipResponse:
    company = await _load_principal_company(session, principal)
    
    vendor = await session.get(Company, body.vendor_company_id)
    if not vendor or vendor.tenant_type not in {"vendor", "esn"}:
        raise HTTPException(status_code=400, detail="Target vendor not found or is not a vendor/ESN.")
    
    existing = await session.scalar(
        select(CompanyPartnership)
        .where(CompanyPartnership.client_company_id == company.id)
        .where(CompanyPartnership.vendor_company_id == body.vendor_company_id)
    )
    if existing:
        return CompanyPartnershipResponse.model_validate(existing)
    
    partnership = CompanyPartnership(
        client_company_id=company.id,
        vendor_company_id=body.vendor_company_id,
        status="active"
    )
    session.add(partnership)
    await session.flush()
    await session.refresh(partnership, attribute_names=["client_company", "vendor_company"])
    return CompanyPartnershipResponse.model_validate(partnership)


@router.get("/me/partnerships", response_model=list[CompanyPartnershipResponse])
async def list_partnerships(
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles("super_admin", "client_admin", "client_exec", "client_pm", "esn_admin", "esn_delivery_manager")
    ),
) -> list[CompanyPartnershipResponse]:
    company = await _load_principal_company(session, principal)
    
    if company.tenant_type == "client":
        stmt = select(CompanyPartnership).where(CompanyPartnership.client_company_id == company.id)
    else:
        stmt = select(CompanyPartnership).where(CompanyPartnership.vendor_company_id == company.id)
        
    result = await session.execute(stmt)
    partnerships = result.scalars().all()
    
    # Refresh to load company relations
    for p in partnerships:
        await session.refresh(p, attribute_names=["client_company", "vendor_company"])
        
    return [CompanyPartnershipResponse.model_validate(p) for p in partnerships]
