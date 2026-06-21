"""FastAPI dependencies for provider-based request authentication."""

from __future__ import annotations

from typing import Optional

from fastapi import Request

from auth.helpers import forbidden, unauthorized
from models.user import User


def get_current_user(request: Request) -> Optional[User]:
    """Return the request-scoped authenticated user, if any."""
    return getattr(request.state, "current_user", None)


def require_user(request: Request) -> User:
    """Require an authenticated current user."""
    user = get_current_user(request)
    if user is None or user.is_disabled:
        raise unauthorized("Authentication required")
    return user


def require_admin(request: Request) -> User:
    """Require an authenticated admin user."""
    user = require_user(request)
    if not user.is_admin:
        raise forbidden("Admin access required")
    return user
