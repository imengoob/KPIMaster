from app.models.trello_list import ListType, TrelloList


def test_trello_list_enum_uses_lowercase_database_values() -> None:
    enum_type = TrelloList.__table__.c.list_type.type
    assert enum_type.enums == ["backlog", "wip", "done", "unknown"]
    assert ListType.UNKNOWN.value == "unknown"
