from pydantic import Field

from app.schemas.common import OrmBase


class CompanyResponse(OrmBase):
    id: int
    name: str
    slug: str
    tenant_type: str
    description: str | None
    contact_email: str | None
    is_active: bool


class CompanyUpdate(OrmBase):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    contact_email: str | None = Field(default=None, max_length=320)
    tenant_type: str | None = None


class CompanyUserCreate(OrmBase):
    username: str = Field(min_length=3, max_length=100)
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(default="company_manager")
    developer_id: int | None = None

class CompanyPartnershipCreate(OrmBase):
    vendor_company_id: int

class CompanyPartnershipResponse(OrmBase):
    id: int
    client_company_id: int
    vendor_company_id: int
    status: str
    vendor_company: CompanyResponse | None = None
    client_company: CompanyResponse | None = None
