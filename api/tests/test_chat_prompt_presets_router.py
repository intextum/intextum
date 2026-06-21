"""Tests for chat prompt preset routes."""

from unittest.mock import AsyncMock, patch

from auth.dependencies import require_admin, require_user
from models.chat.prompt_presets import PromptPreset, PromptPresetListResponse
from models.user import User


def _user() -> User:
    return User(username="user", sub="sub-user", groups=[])


def _admin() -> User:
    return User(username="admin", sub="sub-admin", groups=["admins"])


def _response(*, enabled: bool = True) -> PromptPresetListResponse:
    return PromptPresetListResponse(
        presets=[
            PromptPreset(
                id="demo",
                enabled=enabled,
                sort_order=10,
                mode="research",
                label={"en": "Demo", "de": "Demo"},
                description={"en": "Demo preset", "de": "Demo Preset"},
                prompt={"en": "Do research.", "de": "Recherchiere."},
                icon="book-open",
                context={"min_files": 1, "max_files": 1},
                action="submit",
            )
        ]
    )


def test_public_prompt_presets_returns_enabled_presets(test_client):
    from main import app

    app.dependency_overrides[require_user] = _user
    try:
        with patch(
            "routers.chat_prompt_presets.ChatPromptPresetService.get_presets",
            new=AsyncMock(return_value=_response()),
        ) as get_presets:
            response = test_client.get("/api/chat/prompt-presets")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert response.json()["presets"][0]["mode"] == "research"
    assert get_presets.await_args.kwargs == {"include_disabled": False}


def test_admin_prompt_presets_returns_full_preset_list(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin
    try:
        with patch(
            "routers.admin.chat_prompt_presets.ChatPromptPresetService.get_presets",
            new=AsyncMock(return_value=_response(enabled=False)),
        ) as get_presets:
            response = test_client.get("/api/admin/chat-prompt-presets")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json()["presets"][0]["enabled"] is False
    assert get_presets.await_args.kwargs == {"include_disabled": True}


def test_admin_replace_prompt_presets_passes_admin_username(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin
    try:
        with patch(
            "routers.admin.chat_prompt_presets.ChatPromptPresetService.replace_presets",
            new=AsyncMock(return_value=_response()),
        ) as replace_presets:
            response = test_client.put(
                "/api/admin/chat-prompt-presets",
                json={"presets": [_response().presets[0].model_dump(mode="json")]},
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert replace_presets.await_args.kwargs["updated_by"] == "admin"
    assert replace_presets.await_args.args[0][0].id == "demo"


def test_admin_replace_prompt_presets_rejects_invalid_payload(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin
    try:
        response = test_client.put(
            "/api/admin/chat-prompt-presets",
            json={
                "presets": [
                    {
                        "id": "invalid",
                        "mode": "chat",
                        "label": {"en": "Invalid", "de": "Ungultig"},
                        "description": {"en": "Invalid"},
                        "prompt": {"en": "Run", "de": "Los"},
                    }
                ]
            },
        )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 422


def test_admin_reset_prompt_presets(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin
    try:
        with patch(
            "routers.admin.chat_prompt_presets.ChatPromptPresetService.reset_presets",
            new=AsyncMock(return_value=_response()),
        ) as reset_presets:
            response = test_client.post("/api/admin/chat-prompt-presets/reset")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    reset_presets.assert_awaited_once()
