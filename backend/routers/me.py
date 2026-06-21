"""Authenticated current-user endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from database import get_db
from models.notification_preferences import NotificationPreferences
from models.user import User
from services.notification_preferences import NotificationPreferencesService

router = APIRouter(prefix="/me")


def _require_user_sub(user: User) -> str:
    try:
        return user.require_stable_sub()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication subject missing",
        ) from exc


@router.get("/notification-preferences", response_model=NotificationPreferences)
async def get_notification_preferences(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferences:
    """Return the current user's notification preferences."""
    return await NotificationPreferencesService(db).get_preferences(
        _require_user_sub(user)
    )


@router.put("/notification-preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    preferences: NotificationPreferences,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferences:
    """Persist the current user's notification preferences."""
    return await NotificationPreferencesService(db).update_preferences(
        _require_user_sub(user),
        preferences,
    )
