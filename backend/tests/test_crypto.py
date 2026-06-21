"""Tests for encrypted secret storage helpers."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.crypto import decrypt_value, encrypt_value, is_encrypted_value


def _settings(
    *,
    key: str = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
):
    return SimpleNamespace(ENCRYPTION_KEY=key)


def test_encrypt_value_requires_encryption_key():
    with patch("services.crypto.get_settings", return_value=_settings(key="")):
        with pytest.raises(ValueError, match="ENCRYPTION_KEY must be set"):
            encrypt_value("secret")


def test_encrypt_decrypt_round_trip_uses_envelope_prefix():
    with patch("services.crypto.get_settings", return_value=_settings()):
        ciphertext = encrypt_value("secret")
        assert is_encrypted_value(ciphertext) is True
        assert decrypt_value(ciphertext) == "secret"


def test_decrypt_value_rejects_plaintext_secrets_by_default():
    with patch("services.crypto.get_settings", return_value=_settings()):
        with pytest.raises(ValueError, match="unencrypted secret"):
            decrypt_value("plaintext-secret")
