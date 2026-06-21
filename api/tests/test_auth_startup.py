"""Tests for auth startup helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from auth.startup import bootstrap_local_auth


@pytest.mark.asyncio
async def test_bootstrap_local_auth_skips_when_local_auth_disabled(monkeypatch):
    probe = AsyncMock()
    monkeypatch.setattr("auth.startup.probe_valkey", probe)

    await bootstrap_local_auth(
        SimpleNamespace(AUTH_LOCAL_ENABLED=False),
        session_factory=object(),
    )

    probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_bootstrap_local_auth_requires_configured_valkey(monkeypatch):
    monkeypatch.setattr("auth.startup.is_valkey_configured", lambda: False)

    with pytest.raises(RuntimeError, match="requires VALKEY_URL"):
        await bootstrap_local_auth(
            SimpleNamespace(AUTH_LOCAL_ENABLED=True),
            session_factory=object(),
        )


@pytest.mark.asyncio
async def test_bootstrap_local_auth_requires_reachable_valkey(monkeypatch):
    monkeypatch.setattr("auth.startup.is_valkey_configured", lambda: True)
    monkeypatch.setattr("auth.startup.probe_valkey", AsyncMock(return_value=False))

    with pytest.raises(RuntimeError, match="requires a reachable Valkey"):
        await bootstrap_local_auth(
            SimpleNamespace(AUTH_LOCAL_ENABLED=True),
            session_factory=object(),
        )


@pytest.mark.asyncio
async def test_bootstrap_local_auth_bootstraps_admin_with_internal_context(monkeypatch):
    settings = SimpleNamespace(AUTH_LOCAL_ENABLED=True)
    session_factory = object()
    calls: list[tuple[object, object]] = []

    @asynccontextmanager
    async def fake_rls_session(received_session_factory, received_context):
        assert received_session_factory is session_factory
        assert received_context == ("context", "auth")
        yield "db-session"

    class FakeUserService:
        def __init__(self, db):
            self.db = db

        async def bootstrap_local_admin(self, received_settings):
            calls.append((self.db, received_settings))

    monkeypatch.setattr("auth.startup.is_valkey_configured", lambda: True)
    monkeypatch.setattr("auth.startup.probe_valkey", AsyncMock(return_value=True))
    monkeypatch.setattr("auth.startup.internal_context", lambda name: ("context", name))
    monkeypatch.setattr("auth.startup.rls_session", fake_rls_session)
    monkeypatch.setattr("auth.startup.UserService", FakeUserService)

    await bootstrap_local_auth(settings, session_factory=session_factory)

    assert calls == [("db-session", settings)]
