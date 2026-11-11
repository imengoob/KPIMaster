"""
Unit tests for Fernet-based token encryption/decryption.

These are pure unit tests — no DB, no HTTP, no fixtures needed.
They verify: encrypt → decrypt roundtrip, error paths, and the
safe_decrypt helper that never raises.
"""
import pytest

from app.integrations.encryption import decrypt_token, encrypt_token, safe_decrypt


# ── encrypt_token ─────────────────────────────────────────────────────────────

def test_encrypt_returns_non_empty_string():
    result = encrypt_token("my-secret-token")
    assert isinstance(result, str) and len(result) > 0


def test_encrypted_differs_from_plaintext():
    original = "plain-text-api-key"
    assert encrypt_token(original) != original


def test_encrypted_is_url_safe_base64():
    """Fernet output must only contain URL-safe base64 characters."""
    import re
    result = encrypt_token("test-token-value")
    # Fernet tokens are base64url-encoded; no '+', '/', '=' padding issues
    assert re.match(r"^[A-Za-z0-9_\-=]+$", result)


def test_two_encryptions_of_same_plaintext_differ():
    """Fernet uses a random IV — same plaintext → different ciphertext each time."""
    t1 = encrypt_token("same-secret")
    t2 = encrypt_token("same-secret")
    assert t1 != t2


def test_encrypt_empty_raises_value_error():
    with pytest.raises(ValueError, match="encrypt"):
        encrypt_token("")


def test_encrypt_long_token_succeeds():
    long_token = "x" * 1024
    result = encrypt_token(long_token)
    assert len(result) > 0


# ── decrypt_token ─────────────────────────────────────────────────────────────

def test_decrypt_roundtrip_short():
    original = "ghp_abc123xyz"
    assert decrypt_token(encrypt_token(original)) == original


def test_decrypt_roundtrip_long():
    original = "Bearer " + "a" * 512
    assert decrypt_token(encrypt_token(original)) == original


def test_decrypt_roundtrip_unicode():
    original = "token-with-ünïcödé-chars"
    assert decrypt_token(encrypt_token(original)) == original


def test_decrypt_empty_raises_value_error():
    with pytest.raises(ValueError, match="decrypt"):
        decrypt_token("")


def test_decrypt_garbage_raises_value_error():
    with pytest.raises(ValueError, match="[Dd]ecryption"):
        decrypt_token("not-a-valid-fernet-token-at-all")


def test_decrypt_truncated_token_raises():
    valid = encrypt_token("hello")
    with pytest.raises(ValueError):
        decrypt_token(valid[:10])


def test_decrypt_wrong_key_raises(monkeypatch):
    """Changing the secret key means the old ciphertext cannot be decrypted."""
    ciphertext = encrypt_token("original-secret")
    # Patch the settings secret to a different value
    from app.config import settings
    monkeypatch.setattr(settings, "secret_key", "completely-different-secret-key!!")
    with pytest.raises(ValueError):
        decrypt_token(ciphertext)


# ── safe_decrypt ──────────────────────────────────────────────────────────────

def test_safe_decrypt_none_returns_none():
    assert safe_decrypt(None) is None


def test_safe_decrypt_empty_string_returns_none():
    assert safe_decrypt("") is None


def test_safe_decrypt_garbage_returns_none():
    assert safe_decrypt("garbage-ciphertext-xyz") is None


def test_safe_decrypt_valid_returns_plaintext():
    original = "my-oauth-access-token"
    ciphertext = encrypt_token(original)
    assert safe_decrypt(ciphertext) == original


def test_safe_decrypt_never_raises():
    """safe_decrypt must swallow all errors and return None."""
    # Various bad inputs
    for bad in ["", None, "abc", "===invalid===", "A" * 200]:
        result = safe_decrypt(bad)
        assert result is None or isinstance(result, str)
