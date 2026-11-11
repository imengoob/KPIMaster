"""Repository activity / mismatch response schemas."""
from datetime import datetime

from app.schemas.common import OrmBase


class RepositoryMismatchResponse(OrmBase):
    """
    Matches the frontend BackendRepositoryMismatch interface field-for-field.
    All field names are snake_case as required by the frontend adapter.
    """
    id: int
    ticket_id: int
    project_id: int
    branch_name: str | None
    commit_count: int
    pr_count: int
    pr_merged: bool
    last_commit_at: datetime | None
    mismatch_type: str | None
    mismatch_reason: str | None
    scanned_at: datetime | None


class RepositoryScanResult(OrmBase):
    """Summary returned by POST /repository-mismatches/scan."""
    project_id: int
    mismatches: int
    tickets_scanned: int
    scanned_at: datetime
