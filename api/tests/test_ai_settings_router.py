"""Tests for admin AI settings routes."""

from unittest.mock import AsyncMock, patch

from auth.dependencies import require_admin
from models.ai_settings import AiSettingsResponse, AiSettingEntry
from models.user import User


def _admin_response() -> AiSettingsResponse:
    return AiSettingsResponse(
        items=[
            AiSettingEntry(
                key="chat_model",
                section="chat",
                label="Chat Model",
                description="Model used for chat responses.",
                input_type="text",
                value="admin-chat-model",
                default_value="default-chat-model",
                overridden=True,
            )
        ]
    )


def _admin_user() -> User:
    return User(username="admin", sub="sub-admin", groups=["admins"])


def test_get_ai_settings_returns_admin_payload(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.ai_settings.AiSettingsService.get_admin_response",
            new=AsyncMock(return_value=_admin_response()),
        ):
            response = test_client.get("/api/ai-settings")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["key"] == "chat_model"
    assert payload["items"][0]["value"] == "admin-chat-model"
    assert payload["items"][0]["overridden"] is True


def test_patch_ai_settings_persists_updates_with_admin_username(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.ai_settings.AiSettingsService.update_settings",
            new=AsyncMock(return_value=_admin_response()),
        ) as update_settings:
            response = test_client.patch(
                "/api/ai-settings",
                json={"chat_model": "team-chat-model", "chat_search_limit": 8},
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert update_settings.await_args.args == (
        {"chat_model": "team-chat-model", "chat_search_limit": 8},
    )
    assert update_settings.await_args.kwargs["updated_by"] == "admin"


def test_reset_ai_setting_rejects_unknown_keys(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        response = test_client.delete("/api/ai-settings/not-a-real-setting")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown AI setting"
