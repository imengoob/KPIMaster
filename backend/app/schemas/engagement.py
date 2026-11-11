from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import OrmBase

TenantType = Literal["client", "vendor", "internal"]
EngagementStatus = Literal["draft", "active", "paused", "completed"]
AssignmentStatus = Literal["planned", "active", "ended"]


class EngagementCreate(OrmBase):
    name: str = Field(..., min_length=3, max_length=255)
    vendor_company_id: int
    project_id: int
    description: str | None = Field(default=None, max_length=500)
    starts_on: date | None = None
    ends_on: date | None = None
    sla_response_hours: int = Field(default=8, ge=1, le=168)
    status: EngagementStatus = "active"
    client_company_id: int | None = None
    client_visible: bool = True


class EngagementResponse(OrmBase):
    id: int
    name: str
    status: str
    client_company_id: int
    client_company_name: str
    vendor_company_id: int
    vendor_company_name: str
    project_id: int
    project_name: str
    description: str | None
    starts_on: date | None
    ends_on: date | None
    sla_response_hours: int
    client_visible: bool
    created_at: datetime
    updated_at: datetime


class DeveloperAssignmentCreate(OrmBase):
    developer_id: int
    assignment_role: str = Field(default="developer", min_length=2, max_length=100)
    status: AssignmentStatus = "active"
    allocation_percentage: int = Field(default=100, ge=1, le=100)
    start_date: date
    end_date: date | None = None
    is_primary: bool = True


class DeveloperAssignmentResponse(OrmBase):
    id: int
    developer_id: int
    developer_name: str
    developer_company_id: int | None
    engagement_id: int
    project_id: int
    project_name: str
    client_company_id: int
    client_company_name: str
    vendor_company_id: int
    vendor_company_name: str
    assignment_role: str
    status: str
    allocation_percentage: int
    start_date: date
    end_date: date | None
    is_primary: bool
    created_at: datetime
    updated_at: datetime
