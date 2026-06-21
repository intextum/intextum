"""Password policy validation for local credentials."""

from __future__ import annotations

from collections.abc import Iterable


class PasswordPolicyError(ValueError):
    """Raised when a password does not meet local credential policy."""


COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "123456",
        "1234567",
        "12345678",
        "123456789",
        "1234567890",
        "admin",
        "admin123",
        "changeme",
        "letmein",
        "password",
        "password1",
        "password123",
        "qwerty",
        "qwerty123",
        "test",
        "test123",
        "test1234",
        "welcome",
        "welcome1",
    }
)


def _normalized_common_values(values: Iterable[str]) -> set[str]:
    return {value.strip().lower() for value in values if value.strip()}


def validate_local_password(raw_password: str, settings) -> None:
    """Validate a newly set local password against configured policy."""
    password = raw_password or ""
    min_length = max(1, int(getattr(settings, "AUTH_PASSWORD_MIN_LENGTH", 12)))
    if len(password) < min_length:
        raise PasswordPolicyError(
            f"Password must be at least {min_length} characters long"
        )

    if bool(getattr(settings, "AUTH_PASSWORD_REJECT_COMMON", True)):
        normalized = password.strip().lower()
        if normalized in _normalized_common_values(COMMON_PASSWORDS):
            raise PasswordPolicyError("Password is too common")
