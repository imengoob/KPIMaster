"""
Token encryption / decryption using Fernet symmetric encryption.

Fernet guarantees:
  • AES-128-CBC with PKCS7 padding
  • HMAC-SHA256 authentication
  • Timestamp included in token (detect replay / expiry)

The encryption key is derived from settings.secret_key so no separate
key-management infrastructure is needed for development.  In production,
replace _derive_key() with a call to a KMS (AWS KMS, GCP Cloud KMS, etc.)
and store the data key alongside the ciphertext.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _derive_key() -> bytes:
    """
    Deterministically derive a 32-byte (256-bit) key from settings.secret_key,
    then base64url-encode it for Fernet.
    """
    raw = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(raw)


def _fernet() -> Fernet:
    return Fernet(_derive_key())


def encrypt_token(plaintext: str) -> str:
    """Encrypt a plaintext token string. Returns a URL-safe string."""
    if not plaintext:
        raise ValueError("Cannot encrypt an empty token")
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a previously encrypted token.
    Raises ValueError if the ciphertext is invalid or tampered.
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt an empty ciphertext")
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Token decryption failed — token invalid or key mismatch") from exc


def safe_decrypt(ciphertext: str | None) -> str | None:
    """Like decrypt_token but returns None for missing/invalid values."""
    if not ciphertext:
        return None
    try:
        return decrypt_token(ciphertext)
    except ValueError:
        return None
