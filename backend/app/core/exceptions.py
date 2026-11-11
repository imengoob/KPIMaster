"""
Domain and application exception hierarchy.

All exceptions carry an HTTP status code and a machine-readable error_code
so the API layer can render consistent error responses without any logic.
"""
from typing import Any


class KPIMasterError(Exception):
    """Root exception for all application errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        detail: Any = None,
        *,
        error_code: str | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.detail = detail
        if error_code:
            self.error_code = error_code
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# 404 Not Found
# ---------------------------------------------------------------------------
class NotFoundError(KPIMasterError):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "The requested resource was not found."


class ProjectNotFoundError(NotFoundError):
    error_code = "PROJECT_NOT_FOUND"
    message = "Project not found."


class SprintNotFoundError(NotFoundError):
    error_code = "SPRINT_NOT_FOUND"
    message = "Sprint not found."


class TicketNotFoundError(NotFoundError):
    error_code = "TICKET_NOT_FOUND"
    message = "Ticket not found."


class DeveloperNotFoundError(NotFoundError):
    error_code = "DEVELOPER_NOT_FOUND"
    message = "Developer not found."


# ---------------------------------------------------------------------------
# 409 Conflict
# ---------------------------------------------------------------------------
class ConflictError(KPIMasterError):
    status_code = 409
    error_code = "CONFLICT"
    message = "Resource conflict."


class DuplicateSprintError(ConflictError):
    error_code = "DUPLICATE_SPRINT"
    message = "An active sprint already exists for this project."


# ---------------------------------------------------------------------------
# 422 Validation / Business Rule Violations
# ---------------------------------------------------------------------------
class DomainValidationError(KPIMasterError):
    status_code = 422
    error_code = "DOMAIN_VALIDATION_ERROR"
    message = "Domain validation failed."


class InvalidSprintDateRangeError(DomainValidationError):
    error_code = "INVALID_SPRINT_DATE_RANGE"
    message = "Sprint end date must be after start date."


class TicketQualityError(DomainValidationError):
    error_code = "TICKET_QUALITY_ERROR"
    message = "Ticket does not meet quality requirements."


# ---------------------------------------------------------------------------
# 503 Infrastructure
# ---------------------------------------------------------------------------
class InfrastructureError(KPIMasterError):
    status_code = 503
    error_code = "INFRASTRUCTURE_ERROR"
    message = "An infrastructure dependency is unavailable."


class EventBusError(InfrastructureError):
    error_code = "EVENT_BUS_ERROR"
    message = "Failed to publish or consume events."


class CircuitBreakerOpenError(InfrastructureError):
    error_code = "CIRCUIT_OPEN"
    message = "Circuit breaker is open — downstream service unavailable."
    status_code = 503
