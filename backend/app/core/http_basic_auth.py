from __future__ import annotations

import base64
import hmac


def parse_basic_auth_header(authorization_header: str | None) -> tuple[str, str] | None:
    """
    Parse an HTTP Basic Authorization header.

    Returns (username, password) if valid, otherwise None.
    """
    if not authorization_header:
        return None

    prefix = "Basic "
    if not authorization_header.startswith(prefix):
        return None

    token = authorization_header[len(prefix):].strip()
    if not token:
        return None

    try:
        decoded = base64.b64decode(token).decode("utf-8")
    except Exception:
        return None

    if ":" not in decoded:
        return None

    username, password = decoded.split(":", 1)
    return username, password


def constant_time_credentials_match(
    username: str,
    password: str,
    expected_username: str,
    expected_password: str,
) -> bool:
    """
    Compare credentials using constant-time checks to reduce timing side-channel risk.
    """
    return hmac.compare_digest(username, expected_username) and hmac.compare_digest(password, expected_password)
