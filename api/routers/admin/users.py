"""Admin endpoints for user management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.user import User
from services.password_policy import PasswordPolicyError
from services.user import DuplicateUsernameError, UserService

from .common import (
    CreateUserRequest,
    SetUserPasswordRequest,
    UpdateUserRequest,
    UserEntry,
    user_entry,
)

router = APIRouter()


@router.get("/users")
async def list_users(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserEntry]:
    """List all known users (admin only)."""
    _ = user
    users = await UserService(db).list_users()
    return [user_entry(item) for item in users]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserEntry:
    """Create a local user (admin only)."""
    _ = user
    try:
        created = await UserService(db).create_local_user(
            username=body.username,
            password=body.password,
            email=body.email,
            display_name=body.display_name,
            is_admin=body.is_admin,
            is_disabled=body.is_disabled,
            group_slugs=body.groups,
        )
    except DuplicateUsernameError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user_entry(created)


@router.patch("/users/{user_sub}")
async def update_user(
    user_sub: str,
    body: UpdateUserRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserEntry:
    """Update a canonical app user (admin only)."""
    _ = user
    try:
        updated = await UserService(db).update_user(
            user_sub=user_sub,
            username=body.username,
            email=body.email,
            display_name=body.display_name,
            is_admin=body.is_admin,
            is_disabled=body.is_disabled,
            group_slugs=body.groups,
        )
    except DuplicateUsernameError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_entry(updated)


@router.post("/users/{user_sub}/password")
async def set_user_password(
    user_sub: str,
    body: SetUserPasswordRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset a user's local password (admin only)."""
    _ = user
    svc = UserService(db)
    target = await svc.get_user_by_sub(user_sub)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        await svc.set_password(
            user_sub,
            body.password,
            must_change_password=body.must_change_password,
        )
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"updated": True}
