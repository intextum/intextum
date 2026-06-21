"""Tests for optional shared Valkey helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.valkey as valkey_service
from services.valkey import close_valkey_client, init_valkey_client, probe_valkey


@pytest.fixture(autouse=True)
def reset_valkey_client(monkeypatch):
    monkeypatch.setattr(valkey_service, "_valkey_client", None)
    yield
    monkeypatch.setattr(valkey_service, "_valkey_client", None)


@pytest.mark.asyncio
async def test_init_valkey_client_returns_none_when_unconfigured():
    with patch(
        "services.valkey.get_settings",
        return_value=SimpleNamespace(VALKEY_URL=""),
    ):
        client = await init_valkey_client()

    assert client is None


@pytest.mark.asyncio
async def test_init_valkey_client_reuses_cached_client(monkeypatch):
    cached_client = object()
    monkeypatch.setattr(valkey_service, "_valkey_client", cached_client)

    client = await init_valkey_client()

    assert client is cached_client


@pytest.mark.asyncio
async def test_init_valkey_client_creates_client_from_configured_url(monkeypatch):
    created_client = object()
    async_valkey = SimpleNamespace(
        from_url=MagicMock(return_value=created_client),
    )
    monkeypatch.setattr(valkey_service, "AsyncValkey", async_valkey)

    with patch(
        "services.valkey.get_settings",
        return_value=SimpleNamespace(VALKEY_URL=" valkey://localhost:6379/0 "),
    ):
        client = await init_valkey_client()

    assert client is created_client
    assert valkey_service.get_valkey_client() is created_client
    async_valkey.from_url.assert_called_once_with(
        "valkey://localhost:6379/0",
        decode_responses=True,
    )


@pytest.mark.asyncio
async def test_init_valkey_client_raises_when_dependency_missing(monkeypatch):
    monkeypatch.setattr(valkey_service, "AsyncValkey", None)

    with (
        patch(
            "services.valkey.get_settings",
            return_value=SimpleNamespace(VALKEY_URL="valkey://localhost:6379/0"),
        ),
        pytest.raises(RuntimeError, match="Valkey support requires"),
    ):
        await init_valkey_client()


@pytest.mark.asyncio
async def test_probe_valkey_uses_client_ping_result():
    client = AsyncMock()
    client.ping.return_value = "PONG"

    result = await probe_valkey(client)

    assert result is True
    client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_valkey_returns_false_without_client():
    with patch("services.valkey.init_valkey_client", new=AsyncMock(return_value=None)):
        result = await probe_valkey()

    assert result is False


@pytest.mark.asyncio
async def test_probe_valkey_returns_false_for_falsey_ping_result():
    client = AsyncMock()
    client.ping.return_value = ""

    result = await probe_valkey(client)

    assert result is False
    client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_valkey_client_calls_aclose_and_clears_cache(monkeypatch):
    client = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(valkey_service, "_valkey_client", client)

    await close_valkey_client()

    client.aclose.assert_awaited_once()
    assert valkey_service.get_valkey_client() is None
