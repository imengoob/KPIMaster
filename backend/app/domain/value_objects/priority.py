from enum import IntEnum, StrEnum


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> int:
        """Numeric weight used in KPI and quality-score calculations."""
        return {
            Priority.LOW: 1,
            Priority.MEDIUM: 2,
            Priority.HIGH: 3,
            Priority.CRITICAL: 4,
        }[self]

    @property
    def escalation_sla_hours(self) -> int:
        """Max hours before a blocker at this priority triggers escalation."""
        return {
            Priority.LOW: 72,
            Priority.MEDIUM: 48,
            Priority.HIGH: 24,
            Priority.CRITICAL: 8,
        }[self]


class TicketType(StrEnum):
    FEATURE = "feature"
    STORY = "story"
    BUG = "bug"
    TASK = "task"
    EPIC = "epic"
    SPIKE = "spike"


class SprintStatus(StrEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @property
    def is_active(self) -> bool:
        return self == SprintStatus.ACTIVE


class EscalationLevel(IntEnum):
    DEVELOPER = 1
    TEAM_LEAD = 2
    MANAGEMENT = 3

    @property
    def label(self) -> str:
        return {
            EscalationLevel.DEVELOPER: "Developer",
            EscalationLevel.TEAM_LEAD: "Team Lead",
            EscalationLevel.MANAGEMENT: "Management",
        }[self]
