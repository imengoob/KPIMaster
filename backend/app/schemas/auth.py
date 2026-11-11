from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=200)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    account_type: Literal["company_admin", "client_admin", "esn_admin", "developer"] = "company_admin"
    company_name: str | None = Field(default=None, min_length=2, max_length=255)
    company_slug: str | None = Field(default=None, min_length=2, max_length=120)
    company_type: Literal["client", "vendor"] = "client"


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    company_id: int | None = None
    company_name: str | None = None
    company_slug: str | None = None
    company_type: str | None = None
    developer_id: int | None = None
    kpi_subject_id: int | None = None
    is_active: bool
    is_superuser: bool
