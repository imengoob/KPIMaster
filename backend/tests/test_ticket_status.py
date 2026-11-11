from app.domain.value_objects.ticket_status import TicketStatus


def test_ticket_status_members_are_strings() -> None:
    assert TicketStatus.BACKLOG.value == "backlog"
    assert TicketStatus.IN_PROGRESS.value == "in_progress"


def test_ticket_status_transition_rules() -> None:
    assert TicketStatus.BACKLOG.can_transition_to(TicketStatus.TODO) is True
    assert TicketStatus.DONE.can_transition_to(TicketStatus.TODO) is False
