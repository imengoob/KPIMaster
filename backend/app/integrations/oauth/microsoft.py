"""
Microsoft OAuth 2.0 Authorization Code flow (no MSAL dependency).

Uses the Microsoft identity platform v2.0 endpoints directly via httpx.

Docs:
  https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow
  https://learn.microsoft.com/en-us/graph/api/resources/planner-overview

Required .env variables
───────────────────────
  MICROSOFT_CLIENT_ID       — Azure AD app registration client ID
  MICROSOFT_CLIENT_SECRET   — Azure AD app registration client secret
  MICROSOFT_REDIRECT_URI    — must match exactly what's registered
  MICROSOFT_TENANT_ID       — "common" for multi-tenant (default)
"""
from __future__ import annotations

import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.integrations.base import OAuthTokens

_MS_BASE       = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
_GRAPH_ME_URL  = "https://graph.microsoft.com/v1.0/me"

_SCOPES = [
    "https://graph.microsoft.com/Tasks.ReadWrite",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Group.Read.All",
    "offline_access",        # enables refresh tokens
]


class MicrosoftOAuth:
    """Encapsulates the Microsoft identity platform OAuth 2.0 authorization code flow."""

    def __init__(
        self,
        client_id:     str,
        client_secret: str,
        redirect_uri:  str,
        tenant_id:     str = "common",
    ) -> None:
        self.client_id     = client_id
        self.client_secret = client_secret
        self.redirect_uri  = redirect_uri
        self.tenant_id     = tenant_id
        self._base         = _MS_BASE.format(tenant=tenant_id)

    # ── Step 1: build redirect URL ────────────────────────────────────────────

    def build_authorization_url(self, state: str | None = None) -> tuple[str, str]:
        """Returns (authorization_url, state)."""
        state = state or secrets.token_urlsafe(32)
        params = {
            "client_id":     self.client_id,
            "response_type": "code",
            "redirect_uri":  self.redirect_uri,
            "scope":         " ".join(_SCOPES),
            "state":         state,
            "response_mode": "query",
        }
        url = f"{self._base}/authorize?{urllib.parse.urlencode(params)}"
        return url, state

    # ── Step 2: exchange code for tokens ──────────────────────────────────────

    async def exchange_code(self, code: str) -> OAuthTokens:
        """POST to Microsoft token endpoint and return OAuthTokens."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/token",
                data={
                    "grant_type":    "authorization_code",
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "code":          code,
                    "redirect_uri":  self.redirect_uri,
                    "scope":         " ".join(_SCOPES),
                },
            )
        resp.raise_for_status()
        return self._parse_token_response(resp.json())

    # ── Step 3: refresh an expired access token ───────────────────────────────

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """Exchange a refresh_token for a new access_token."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/token",
                data={
                    "grant_type":    "refresh_token",
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "scope":         " ".join(_SCOPES),
                },
            )
        resp.raise_for_status()
        return self._parse_token_response(resp.json())

    # ── Step 4: fetch user profile ────────────────────────────────────────────

    async def get_user_profile(self, access_token: str) -> dict[str, Any]:
        """Return /me from Microsoft Graph (id, displayName, mail, etc.)."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                _GRAPH_ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        resp.raise_for_status()
        return resp.json()

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
            extra={"tenant_id": data.get("tenant_id", "common")},
        )


def get_microsoft_oauth() -> MicrosoftOAuth:
    """Return a MicrosoftOAuth configured from app settings."""
    from fastapi import HTTPException
    from app.config import settings

    client_id     = settings.microsoft_client_id
    client_secret = settings.microsoft_client_secret
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Microsoft OAuth is not configured on this server. "
                "Set MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET in the backend .env file."
            ),
        )
    return MicrosoftOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=settings.microsoft_redirect_uri,
        tenant_id=settings.microsoft_tenant_id,
    )
