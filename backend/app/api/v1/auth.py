from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select

from app.api.dependencies import DbSession
from app.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.company import Company
from app.models.developer import Developer
from app.models.user import User
from app.schemas.auth import AuthTokenResponse, LoginRequest, RegisterRequest, UserRead

router = APIRouter(prefix="/auth", tags=["Auth"])
_SLUG_RE = re.compile(r"[^a-z0-9]+")


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


def _slugify_company_name(name: str, fallback: str) -> str:
    base = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return base or _SLUG_RE.sub("-", fallback.strip().lower()).strip("-") or "company"


async def _unique_company_slug(session: DbSession, seed: str) -> str:
    slug = seed
    counter = 1
    while await session.scalar(select(Company).where(Company.slug == slug)):
        counter += 1
        slug = f"{seed[:110]}-{counter}"
    return slug


@router.post("/register", response_model=UserRead, status_code=201)
async def register(body: RegisterRequest, session: DbSession) -> UserRead:
    existing = await session.scalar(
        select(User).where(or_(User.username == body.username, User.email == body.email))
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists.")

    company: Company | None = None
    developer: Developer | None = None

    if body.account_type == "developer":
        if not body.company_slug:
            raise HTTPException(status_code=422, detail="company_slug is required for developer accounts.")

        company = await session.scalar(select(Company).where(Company.slug == body.company_slug.strip().lower()))
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found for the provided company_slug.")

        developer = await session.scalar(
            select(Developer).where(
                Developer.email == body.email.lower().strip(),
                or_(Developer.company_id == company.id, Developer.company_id.is_(None)),
            )
        )
        if developer is None:
            raise HTTPException(
                status_code=404,
                detail="No tracked developer profile matches this email inside the selected company.",
            )
        linked_user = await session.scalar(select(User).where(User.developer_id == developer.id))
        if linked_user is not None:
            raise HTTPException(status_code=409, detail="This developer already has an account.")
        if developer.company_id is None:
            developer.company_id = company.id
    else:
        company_name = (body.company_name or f"{body.username}'s company").strip()
        company = Company(
            name=company_name,
            slug=await _unique_company_slug(session, _slugify_company_name(company_name, body.username)),
            tenant_type=body.company_type,
            contact_email=body.email.lower().strip(),
            is_active=True,
        )
        session.add(company)
        await session.flush()

    user = User(
        username=body.username.strip(),
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        role="company_admin" if body.account_type == "company_admin" else body.account_type,
        company_id=company.id if company else None,
        developer_id=developer.id if developer else None,
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    await session.refresh(user, attribute_names=["company", "developer"])
    return _to_user_read(user)


@router.post("/login", response_model=AuthTokenResponse)
async def login(body: LoginRequest, session: DbSession) -> AuthTokenResponse:
    user = await session.scalar(select(User).where(User.username == body.username.strip()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive.")

    expires_minutes = settings.auth_access_token_expire_minutes
    token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=expires_minutes),
    )
    return AuthTokenResponse(
        access_token=token,
        expires_in_seconds=expires_minutes * 60,
    )


@router.get("/me", response_model=UserRead)
async def me(request: Request, session: DbSession) -> UserRead:
    user_id = getattr(request.state, "auth_user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    user = await session.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid user.")
    await session.refresh(user, attribute_names=["company", "developer"])
    return _to_user_read(user)
