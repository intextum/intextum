"""Tests for current-user notification preference routes."""

from unittest.mock import AsyncMock, patch

from models.notification_preferences import NotificationPreferences


def _preferences() -> NotificationPreferences:
    return NotificationPreferences.model_validate(
        {
            "chat": {"completed": True, "failed": True, "cancelled": False},
            "content_processing": {"completed": False, "failed": True},
            "research": {"completed": True, "failed": True, "cancelled": False},
        }
    )


def test_get_notification_preferences_returns_current_user_settings(test_client):
    with patch(
        "routers.me.NotificationPreferencesService.get_preferences",
        new=AsyncMock(return_value=_preferences()),
    ) as get_preferences:
        response = test_client.get("/api/me/notification-preferences")

    assert response.status_code == 200
    assert response.json()["chat"]["completed"] is True
    assert response.json()["content_processing"]["completed"] is False
    assert response.json()["research"]["completed"] is True
    get_preferences.assert_awaited_once_with("sub-testuser")


def test_put_notification_preferences_persists_payload(test_client):
    payload = {
        "chat": {"completed": False, "failed": True, "cancelled": True},
        "content_processing": {"completed": True, "failed": False},
        "research": {"completed": False, "failed": True, "cancelled": True},
    }

    with patch(
        "routers.me.NotificationPreferencesService.update_preferences",
        new=AsyncMock(return_value=NotificationPreferences.model_validate(payload)),
    ) as update_preferences:
        response = test_client.put("/api/me/notification-preferences", json=payload)

    assert response.status_code == 200
    assert response.json() == payload
    assert update_preferences.await_args.args[0] == "sub-testuser"
    assert update_preferences.await_args.args[
        1
    ] == NotificationPreferences.model_validate(payload)
