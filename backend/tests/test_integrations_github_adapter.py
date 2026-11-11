from __future__ import annotations

import pytest

from app.integrations.base import ProviderType
from app.integrations.providers.github.adapter import GitHubAdapter


class FakeGitHubClient:
    def __init__(self) -> None:
        self.closed = False

    async def validate(self) -> bool:
        return True

    async def get_repositories(self):
        return [
            {
                "full_name": "acme/api",
                "name": "api",
                "html_url": "https://github.com/acme/api",
                "description": "Service",
                "archived": False,
                "private": True,
            }
        ]

    async def get_issues(self, owner: str, repo: str):
        assert (owner, repo) == ("acme", "api")
        return [
            {
                "id": 1,
                "number": 12,
                "title": "Fix deploy",
                "state": "open",
                "body": "CI is red",
                "labels": [{"name": "blocked"}, {"name": "points: 3"}, {"name": "priority: high"}],
                "assignees": [{"login": "alice"}],
                "created_at": "2026-04-20T10:00:00Z",
                "updated_at": "2026-04-21T10:00:00Z",
            },
            {
                "id": 2,
                "number": 13,
                "title": "Add GitHub sync",
                "state": "closed",
                "labels": [],
                "assignees": [{"login": "bob"}],
                "pull_request": {"url": "https://api.github.com/repos/acme/api/pulls/13"},
                "created_at": "2026-04-20T10:00:00Z",
                "closed_at": "2026-04-22T10:00:00Z",
            },
        ]

    async def get_issue_comments(self, owner: str, repo: str, issue_number: int):
        assert (owner, repo, issue_number) == ("acme", "api", 12)
        return [
            {
                "id": 99,
                "body": "Any update?",
                "user": {"login": "reviewer"},
                "created_at": "2026-04-21T12:00:00Z",
            }
        ]

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def adapter(monkeypatch):
    fake = FakeGitHubClient()
    from app.integrations.providers.github import adapter as adapter_module

    monkeypatch.setattr(adapter_module, "GitHubClient", lambda access_token: fake)
    instance = GitHubAdapter(access_token="token", account_id=1)
    instance._client = fake
    return instance


async def test_maps_repositories_to_boards(adapter: GitHubAdapter) -> None:
    boards = await adapter.get_boards()
    assert boards[0].id == "acme/api"
    assert boards[0].provider == ProviderType.GITHUB
    assert boards[0].extra["private"] is True


async def test_maps_issues_and_pull_requests_to_tasks(adapter: GitHubAdapter) -> None:
    tasks = await adapter.get_tasks("acme/api")
    issue, pull_request = tasks

    assert issue.id == "acme/api#12"
    assert issue.status == "blocked"
    assert issue.priority == "high"
    assert issue.story_points == 3
    assert issue.assignee_ids == ["alice"]

    assert pull_request.task_type == "pull_request"
    assert pull_request.status == "done"
    assert pull_request.assignee_ids == ["bob"]


async def test_maps_issue_comments(adapter: GitHubAdapter) -> None:
    comments = await adapter.get_comments("acme/api#12")
    assert comments[0].provider == ProviderType.GITHUB
    assert comments[0].author_id == "reviewer"
    assert comments[0].body == "Any update?"

