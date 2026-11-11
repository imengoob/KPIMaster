from enum import StrEnum


class TicketStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

    # ── Transition guards ───────────────────────────────────────────────────

    @classmethod
    def allowed_transitions(cls) -> dict["TicketStatus", set["TicketStatus"]]:
        return {
            cls.BACKLOG: {cls.TODO, cls.IN_PROGRESS, cls.CANCELLED},
            cls.TODO: {cls.IN_PROGRESS, cls.BACKLOG, cls.CANCELLED},
            cls.IN_PROGRESS: {cls.IN_REVIEW, cls.BLOCKED, cls.TODO, cls.DONE},
            cls.IN_REVIEW: {cls.IN_PROGRESS, cls.DONE, cls.BLOCKED},
            cls.BLOCKED: {cls.IN_PROGRESS, cls.CANCELLED},
            cls.DONE: set(),
            cls.CANCELLED: set(),
        }

    def can_transition_to(self, target: "TicketStatus") -> bool:
        return target in self.allowed_transitions().get(self, set())

    @property
    def is_terminal(self) -> bool:
        return self in (TicketStatus.DONE, TicketStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self in (TicketStatus.IN_PROGRESS, TicketStatus.IN_REVIEW)

    @property
    def counts_as_stalled(self) -> bool:
        """Tickets in these states are candidates for stall detection."""
        return self in (
            TicketStatus.IN_PROGRESS,
            TicketStatus.IN_REVIEW,
            TicketStatus.BLOCKED,
        )
