"""Shared payload helpers for auth-related responses."""

from __future__ import annotations

from typing import Any

from models.user import User


def user_payload(user: User | None) -> dict[str, Any]:
    """Serialize the current request user for API responses."""
    if user is None:
        return {
            "sub": None,
            "username": "anonymous",
            "email": None,
            "groups": [],
            "preferred_username": None,
            "uid": None,
            "gids": [],
            "is_admin": False,
            "must_change_password": False,
            "auth_provider": "anonymous",
        }

    return {
        "sub": user.sub,
        "username": user.username,
        "email": user.email,
        "groups": user.groups,
        "preferred_username": user.preferred_username,
        "uid": user.uid,
        "gids": user.gids,
        "is_admin": user.is_admin,
        "must_change_password": user.must_change_password,
        "auth_provider": user.auth_provider,
    }
