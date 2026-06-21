"""User model for request authentication context."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    """Represents the current authenticated app user."""

    username: str
    sub: Optional[str] = None
    email: Optional[str] = None
    groups: list[str] = field(default_factory=list)
    auth_provider: str = "anonymous"
    is_admin: bool = False
    is_disabled: bool = False
    must_change_password: bool = False
    csrf_token: Optional[str] = None
    preferred_username: Optional[str] = None
    uid: Optional[int] = None
    gids: list[int] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Get the best display name for the user."""
        return self.preferred_username or self.username

    @property
    def normalized_sub(self) -> Optional[str]:
        """Return the normalized stable subject identifier when present."""
        sub = (self.sub or "").strip()
        return sub or None

    def require_stable_sub(self) -> str:
        """Return the stable subject identifier or raise if unavailable."""
        sub = self.normalized_sub
        if sub is None:
            raise ValueError(
                "Authenticated user is missing a stable subject identifier"
            )
        return sub

    def is_in_group(self, group: str) -> bool:
        """Check if user is in a specific group."""
        return group.lower() in [g.lower() for g in self.groups]

    def is_in_any_group(self, groups: list[str]) -> bool:
        """Check if user is in any of the specified groups."""
        user_groups_lower = [g.lower() for g in self.groups]
        return any(g.lower() in user_groups_lower for g in groups)

    def __str__(self) -> str:
        return (
            f"User({self.username}, sub={self.sub}, uid={self.uid}, "
            f"provider={self.auth_provider}, admin={self.is_admin}, "
            f"groups={self.groups}, gids={self.gids})"
        )
