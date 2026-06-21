"""Fernet-based encryption helpers for secrets at rest."""

from cryptography.fernet import Fernet

from config import get_settings

SECRET_PREFIX = "fernet:"


def _cipher() -> Fernet | None:
    key = get_settings().ENCRYPTION_KEY
    if not key:
        return None
    return Fernet(key.encode())


def _require_cipher() -> Fernet:
    cipher = _cipher()
    if cipher is None:
        raise ValueError("ENCRYPTION_KEY must be set to store encrypted secrets")
    return cipher


def is_encrypted_value(value: str) -> bool:
    """Return True when a stored secret uses the managed encryption envelope."""
    return value.startswith(SECRET_PREFIX)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string, return URL-safe base64 ciphertext."""
    if not plaintext:
        return plaintext
    cipher = _require_cipher()
    ciphertext = cipher.encrypt(plaintext.encode()).decode()
    return f"{SECRET_PREFIX}{ciphertext}"


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    if not ciphertext:
        return ciphertext
    if is_encrypted_value(ciphertext):
        cipher = _cipher()
        if cipher is None:
            raise ValueError("ENCRYPTION_KEY must be set to decrypt stored secrets")
        payload = ciphertext[len(SECRET_PREFIX) :]
        return cipher.decrypt(payload.encode()).decode()
    raise ValueError(
        "Encountered an unencrypted secret in the database. "
        "Re-enter the secret after configuring ENCRYPTION_KEY."
    )
