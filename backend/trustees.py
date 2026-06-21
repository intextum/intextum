"""Trustee helpers shared by RLS and in-memory ACL checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.user import User


def build_user_trustees(user: "User | None") -> list[str]:
    """Build effective trustees for content visibility checks."""
    trustees: list[str] = ["everyone"]
    if user is None:
        return trustees

    if user.normalized_sub:
        trustees.append(f"sub:{user.normalized_sub}")
    for group in user.groups:
        normalized = group.strip().lower()
        if normalized:
            trustees.append(f"group:{normalized}")
    if user.is_admin:
        trustees.append("__acl_admin__")
    return trustees
