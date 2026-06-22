"""Tests for the admin general-settings router and URL normalization."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from models.general_settings import GeneralSettings
from services.general_settings import GeneralSettingsService, _normalize_base_url


def test_normalize_base_url_trims_and_clears():
    assert (
        _normalize_base_url("  https://intextum.example.org/  ")
        == "https://intextum.example.org"
    )
    assert (
        _normalize_base_url("https://intextum.example.org///")
        == "https://intextum.example.org"
    )
    assert _normalize_base_url("") is None
    assert _normalize_base_url(None) is None


@pytest.mark.asyncio
async def test_public_base_url_falls_back_to_server_config():
    service = GeneralSettingsService(db=SimpleNamespace())
    with (
        patch.object(
            GeneralSettingsService, "_load_override", new=AsyncMock(return_value=None)
        ),
        patch(
            "services.general_settings._config_public_base_url",
            return_value="https://config.example.org",
        ),
    ):
        assert await service.get_public_base_url() == "https://config.example.org"


@pytest.mark.asyncio
async def test_admin_override_wins_over_server_config():
    service = GeneralSettingsService(db=SimpleNamespace())
    with (
        patch.object(
            GeneralSettingsService,
            "_load_override",
            new=AsyncMock(return_value="https://override.example.org"),
        ),
        patch(
            "services.general_settings._config_public_base_url",
            return_value="https://config.example.org",
        ),
    ):
        assert await service.get_public_base_url() == "https://override.example.org"


def test_get_general_settings_returns_configured_value(test_client):
    with patch(
        "routers.admin.general_settings.GeneralSettingsService.get_settings",
        new=AsyncMock(
            return_value=GeneralSettings(public_base_url="https://intextum.example.org")
        ),
    ):
        response = test_client.get("/api/general-settings")

    assert response.status_code == 200
    assert response.json()["public_base_url"] == "https://intextum.example.org"


def test_update_general_settings_persists_normalized_value(test_client):
    with patch(
        "routers.admin.general_settings.GeneralSettingsService.update_settings",
        new=AsyncMock(
            return_value=GeneralSettings(public_base_url="https://intextum.example.org")
        ),
    ) as update_settings:
        response = test_client.put(
            "/api/general-settings",
            json={"public_base_url": "https://intextum.example.org/"},
        )

    assert response.status_code == 200
    assert response.json()["public_base_url"] == "https://intextum.example.org"
    assert update_settings.await_count == 1
