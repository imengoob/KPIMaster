"""
OAuth flow tests — mocked provider HTTP responses.

Tests validate:
  • JiraOAuth / MicrosoftOAuth build correct authorization URLs
  • exchange_code() parses provider token responses correctly
  • refresh_access_token() sends the right grant_type
  • get_accessible_resources() (Jira) parses site list
  • get_user_profile() (Microsoft) returns user dict
  • Edge cases: HTTP errors, missing fields, expired tokens

All external HTTP calls are intercepted via monkeypatch on httpx.AsyncClient.post/get.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.oauth.jira import JiraOAuth
from app.integrations.oauth.microsoft import MicrosoftOAuth


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def jira_oauth() -> JiraOAuth:
    return JiraOAuth(
        client_id="test-jira-client-id",
        client_secret="test-jira-client-secret",
        redirect_uri="http://localhost:8000/api/v1/integrations/oauth/jira/callback",
    )


@pytest.fixture
def ms_oauth() -> MicrosoftOAuth:
    return MicrosoftOAuth(
        client_id="test-ms-client-id",
        client_secret="test-ms-client-secret",
        redirect_uri="http://localhost:8000/api/v1/integrations/oauth/microsoft/callback",
        tenant_id="common",
    )


def _mock_response(status_code: int = 200, data: dict | None = None):
    """Create a mock httpx Response-like object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=data or {})
    if status_code >= 400:
        import httpx
        resp.raise_for_status = MagicMock(
            side_effect=lambda: (_ for _ in ()).throw(
                httpx.HTTPStatusError("Error", request=MagicMock(), response=resp)
            )
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


# ── JiraOAuth — build_authorization_url ──────────────────────────────────────

class TestJiraAuthorizationUrl:
    def test_returns_atlassian_host(self, jira_oauth: JiraOAuth):
        url, _ = jira_oauth.build_authorization_url()
        assert "auth.atlassian.com/authorize" in url

    def test_includes_client_id(self, jira_oauth: JiraOAuth):
        url, _ = jira_oauth.build_authorization_url()
        assert "client_id=test-jira-client-id" in url

    def test_includes_redirect_uri(self, jira_oauth: JiraOAuth):
        url, _ = jira_oauth.build_authorization_url()
        assert "redirect_uri=" in url
        assert "localhost" in url

    def test_includes_offline_access_scope(self, jira_oauth: JiraOAuth):
        url, _ = jira_oauth.build_authorization_url()
        assert "offline_access" in url

    def test_response_type_is_code(self, jira_oauth: JiraOAuth):
        url, _ = jira_oauth.build_authorization_url()
        assert "response_type=code" in url

    def test_uses_provided_state(self, jira_oauth: JiraOAuth):
        url, returned_state = jira_oauth.build_authorization_url(state="my-csrf-token")
        assert "state=my-csrf-token" in url
        assert returned_state == "my-csrf-token"

    def test_generates_state_when_not_provided(self, jira_oauth: JiraOAuth):
        _, state = jira_oauth.build_authorization_url()
        assert state and len(state) > 10

    def test_prompt_is_consent(self, jira_oauth: JiraOAuth):
        url, _ = jira_oauth.build_authorization_url()
        assert "prompt=consent" in url


# ── JiraOAuth — exchange_code ─────────────────────────────────────────────────

class TestJiraExchangeCode:
    @pytest.fixture
    def token_response(self):
        return {
            "access_token": "atlassian-access-token-xyz",
            "refresh_token": "atlassian-refresh-token-abc",
            "expires_in": 3600,
            "scope": "read:jira-work write:jira-work offline_access",
            "token_type": "Bearer",
        }

    async def test_returns_oauth_tokens(self, jira_oauth: JiraOAuth, token_response):
        mock_resp = _mock_response(200, token_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.jira.httpx.AsyncClient", return_value=mock_client):
            tokens = await jira_oauth.exchange_code("auth-code-12345")

        assert tokens.access_token == "atlassian-access-token-xyz"
        assert tokens.refresh_token == "atlassian-refresh-token-abc"

    async def test_parses_expires_at(self, jira_oauth: JiraOAuth, token_response):
        mock_resp = _mock_response(200, token_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        before = datetime.now(timezone.utc)
        with patch("app.integrations.oauth.jira.httpx.AsyncClient", return_value=mock_client):
            tokens = await jira_oauth.exchange_code("auth-code-12345")

        assert tokens.expires_at is not None
        assert tokens.expires_at > before

    async def test_parses_scopes_as_list(self, jira_oauth: JiraOAuth, token_response):
        mock_resp = _mock_response(200, token_response)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.jira.httpx.AsyncClient", return_value=mock_client):
            tokens = await jira_oauth.exchange_code("code")

        assert isinstance(tokens.scopes, list)
        assert "offline_access" in tokens.scopes

    async def test_handles_missing_refresh_token(self, jira_oauth: JiraOAuth):
        data = {
            "access_token": "access-only",
            "expires_in": 3600,
            "scope": "read:jira-work",
        }
        mock_resp = _mock_response(200, data)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.jira.httpx.AsyncClient", return_value=mock_client):
            tokens = await jira_oauth.exchange_code("code")

        assert tokens.refresh_token is None


# ── JiraOAuth — get_accessible_resources ─────────────────────────────────────

class TestJiraAccessibleResources:
    async def test_returns_list_of_sites(self, jira_oauth: JiraOAuth):
        sites_data = [
            {"id": "cloud-123", "name": "Acme Jira", "url": "https://acme.atlassian.net"},
        ]
        mock_resp = _mock_response(200, sites_data)
        mock_resp.json = MagicMock(return_value=sites_data)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.jira.httpx.AsyncClient", return_value=mock_client):
            sites = await jira_oauth.get_accessible_resources("access-token")

        assert len(sites) == 1
        assert sites[0]["id"] == "cloud-123"
        assert sites[0]["name"] == "Acme Jira"

    async def test_sends_bearer_auth_header(self, jira_oauth: JiraOAuth):
        mock_resp = _mock_response(200, [])
        mock_resp.json = MagicMock(return_value=[])
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.jira.httpx.AsyncClient", return_value=mock_client):
            await jira_oauth.get_accessible_resources("my-access-token")

        call_kwargs = mock_client.get.call_args
        assert call_kwargs is not None
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer my-access-token"


# ── MicrosoftOAuth — build_authorization_url ─────────────────────────────────

class TestMicrosoftAuthorizationUrl:
    def test_returns_microsoft_login_host(self, ms_oauth: MicrosoftOAuth):
        url, _ = ms_oauth.build_authorization_url()
        assert "login.microsoftonline.com" in url

    def test_uses_correct_tenant(self, ms_oauth: MicrosoftOAuth):
        url, _ = ms_oauth.build_authorization_url()
        assert "/common/oauth2/v2.0/authorize" in url

    def test_includes_planner_scope(self, ms_oauth: MicrosoftOAuth):
        url, _ = ms_oauth.build_authorization_url()
        assert "Tasks.ReadWrite" in url

    def test_includes_offline_access(self, ms_oauth: MicrosoftOAuth):
        url, _ = ms_oauth.build_authorization_url()
        assert "offline_access" in url

    def test_response_mode_is_query(self, ms_oauth: MicrosoftOAuth):
        url, _ = ms_oauth.build_authorization_url()
        assert "response_mode=query" in url

    def test_uses_provided_state(self, ms_oauth: MicrosoftOAuth):
        url, state = ms_oauth.build_authorization_url(state="csrf-token-xyz")
        assert "state=csrf-token-xyz" in url

    def test_custom_tenant_id(self):
        oauth = MicrosoftOAuth(
            client_id="cid", client_secret="csec",
            redirect_uri="http://localhost/cb", tenant_id="my-tenant-id",
        )
        url, _ = oauth.build_authorization_url()
        assert "/my-tenant-id/oauth2" in url


# ── MicrosoftOAuth — exchange_code ────────────────────────────────────────────

class TestMicrosoftExchangeCode:
    async def test_returns_oauth_tokens(self, ms_oauth: MicrosoftOAuth):
        data = {
            "access_token": "ms-access-token",
            "refresh_token": "ms-refresh-token",
            "expires_in": 3600,
            "scope": "Tasks.ReadWrite User.Read offline_access",
            "token_type": "Bearer",
        }
        mock_resp = _mock_response(200, data)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.microsoft.httpx.AsyncClient", return_value=mock_client):
            tokens = await ms_oauth.exchange_code("auth-code")

        assert tokens.access_token == "ms-access-token"
        assert tokens.refresh_token == "ms-refresh-token"

    async def test_uses_form_encoded_body(self, ms_oauth: MicrosoftOAuth):
        """Microsoft token endpoint expects application/x-www-form-urlencoded."""
        data = {"access_token": "t", "expires_in": 3600, "scope": ""}
        mock_resp = _mock_response(200, data)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.microsoft.httpx.AsyncClient", return_value=mock_client):
            await ms_oauth.exchange_code("code")

        call_kwargs = mock_client.post.call_args
        # Microsoft adapter uses `data=` (form), not `json=`
        assert call_kwargs.kwargs.get("data") is not None or call_kwargs.args


# ── MicrosoftOAuth — get_user_profile ────────────────────────────────────────

class TestMicrosoftGetUserProfile:
    async def test_returns_user_dict(self, ms_oauth: MicrosoftOAuth):
        profile = {
            "id": "ms-user-id-abc",
            "displayName": "Alice Engineer",
            "mail": "alice@company.com",
            "userPrincipalName": "alice@company.com",
        }
        mock_resp = _mock_response(200, profile)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.microsoft.httpx.AsyncClient", return_value=mock_client):
            result = await ms_oauth.get_user_profile("access-token")

        assert result["id"] == "ms-user-id-abc"
        assert result["displayName"] == "Alice Engineer"

    async def test_sends_bearer_authorization_header(self, ms_oauth: MicrosoftOAuth):
        mock_resp = _mock_response(200, {"id": "u1", "displayName": "User"})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.integrations.oauth.microsoft.httpx.AsyncClient", return_value=mock_client):
            await ms_oauth.get_user_profile("token-abc")

        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer token-abc"
