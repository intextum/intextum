"""Tests for per-user notification preference storage."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.notification_preferences import NotificationPreferences
from models.sqlalchemy_models import UserNotificationPreference
from services.notification_preferences import NotificationPreferencesService


def _db_with_row(row: UserNotificationPreference | None) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=row))
    return db


@pytest.mark.asyncio
async def test_get_preferences_returns_defaults_without_row():
    preferences = await NotificationPreferencesService(
        _db_with_row(None)
    ).get_preferences("sub-testuser")

    assert preferences == NotificationPreferences()


@pytest.mark.asyncio
async def test_get_preferences_returns_stored_values():
    row = UserNotificationPreference(
        user_sub="sub-testuser",
        preferences_json={
            "chat": {"completed": False, "failed": True, "cancelled": True},
            "content_processing": {"completed": True, "failed": False},
            "research": {"completed": False, "failed": True, "cancelled": True},
        },
    )

    preferences = await NotificationPreferencesService(
        _db_with_row(row)
    ).get_preferences("sub-testuser")

    assert preferences.chat.completed is False
    assert preferences.chat.cancelled is True
    assert preferences.content_processing.completed is True
    assert preferences.content_processing.failed is False
    assert preferences.research.completed is False
    assert preferences.research.cancelled is True


@pytest.mark.asyncio
async def test_update_preferences_deletes_default_row():
    row = UserNotificationPreference(
        user_sub="sub-testuser",
        preferences_json=NotificationPreferences().model_dump(mode="json"),
    )
    db = _db_with_row(row)

    saved = await NotificationPreferencesService(db).update_preferences(
        "sub-testuser",
        NotificationPreferences(),
    )

    assert saved == NotificationPreferences()
    db.delete.assert_awaited_once_with(row)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_preferences_upserts_non_default_values():
    db = _db_with_row(None)
    requested = NotificationPreferences.model_validate(
        {
            "chat": {"completed": True, "failed": False, "cancelled": False},
            "content_processing": {"completed": True, "failed": True},
            "research": {"completed": True, "failed": False, "cancelled": False},
        }
    )

    saved = await NotificationPreferencesService(db).update_preferences(
        "sub-testuser",
        requested,
    )

    assert saved == requested
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert isinstance(added, UserNotificationPreference)
    assert added.user_sub == "sub-testuser"
    assert added.preferences_json == requested.model_dump(mode="json")
    db.commit.assert_awaited_once()
