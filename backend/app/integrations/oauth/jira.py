"""
Jira (Atlassian) OAuth 2.0 Three-Legged (3LO) flow.

Atlassian docs:
  https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/

Flow
────
  1. Redirect user → Atlassian consent page  (build_authorization_url)
  2. Atlassian calls our callback with ?code=  (exchange_code)
  3. We fetch accessible cloud sites           (get_accessible_resources)
  4. Persist tokens + cloud_id in IntegrationAccount

Required .env variables
───────────────────────
  JIRA_CLIENT_ID        — from Atlassian Developer Console app
  JIRA_CLIENT_SECRET    — idem
  JIRA_REDIRECT_URI     — must match exactly what's registered (e.g.
                          https://yourapp.com/api/v1/integrations/oauth/jira/callback)
"""
from __future__ import annotations

import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.integrations.base import OAuthTokens

# ── Atlassian OAuth endpoints ─────────────────────────────────────────────────
_AUTH_URL   = "https://auth.atlassian.com/authorize"
_TOKEN_URL  = "https://auth.atlassian.com/oauth/token"
_SITES_URL  = "https://api.atlassian.com/oauth/token/accessible-resources"

# ── Required scopes ───────────────────────────────────────────────────────────
_SCOPES = [
    "read:jira-work",
    "write:jira-work",
    "read:jira-user",
    "offline_access",        # enables refresh tokens
    "read:board-scope:jira-software",
    "read:sprint:jira-software",
]


class JiraOAuth:
    """Encapsulates the Jira OAuth 2.0 3LO authorization code flow."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.client_id     = client_id
        self.client_secret = client_secret
        self.redirect_uri  = redirect_uri

    # ── Step 1: build redirect URL ────────────────────────────────────────────

    def build_authorization_url(self, state: str | None = None) -> tuple[str, str]:
        """
        Returns (authorization_url, state).
        Pass the state value to the user's session for CSRF verification.
        """
        state = state or secrets.token_urlsafe(32)
        params = {
            "audience":      "api.atlassian.com",
            "client_id":     self.client_id,
            "scope":         " ".join(_SCOPES),
            "redirect_uri":  self.redirect_uri,
            "state":         state,
            "response_type": "code",
            "prompt":        "consent",
        }
        url = f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return url, state

    # ── Step 2: exchange authorization code for tokens ────────────────────────

    async def exchange_code(self, code: str) -> OAuthTokens:
        """POST to Atlassian token endpoint and return normalized OAuthTokens."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                json={
                    "grant_type":    "authorization_code",
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "code":          code,
                    "redirect_uri":  self.redirect_uri,
                },
                headers={"Content-Type": "application/json"},
            )
        resp.raise_for_status()
        data = resp.json()
        return self._parse_token_response(data)

    # ── Step 3: refresh an expired access token ───────────────────────────────

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """Use the refresh_token to get a new access_token."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _TOKEN_URL,
                json={
                    "grant_type":    "refresh_token",
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/json"},
            )
        resp.raise_for_status()
        data = resp.json()
        return self._parse_token_response(data)

    # ── Step 4: discover accessible Jira Cloud sites ──────────────────────────

    async def get_accessible_resources(self, access_token: str) -> list[dict[str, Any]]:
        """
        Returns a list of Atlassian Cloud sites the token can access.
        Each item has: id (cloud_id), name, url, scopes, avatarUrl.
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _SITES_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        resp.raise_for_status()
        return resp.json()  # list[dict]

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_token_response(data: dict[str, Any]) -> OAuthTokens:
        expires_in = data.get("expires_in")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            if expires_in
            else None
        )
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scopes=data.get("scope", "").split(),
        )


# ── Module-level factory using settings ───────────────────────────────────────

def get_jira_oauth(client_id, client_secret ) -> JiraOAuth:
    """Return a JiraOAuth configured from app settings."""
    from fastapi import HTTPException
    from app.config import settings

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Jira OAuth is not configured on this server. "
            ),
        )
    return JiraOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=settings.jira_redirect_uri,
    )
