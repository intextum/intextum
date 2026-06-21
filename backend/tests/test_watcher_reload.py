"""Regression tests for datasource watcher reload behavior."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from auth.dependencies import require_admin
from models.connector_types import LocalFsDataConnector
from models.user import User
from services.watcher import WatcherService


def _admin_user() -> User:
    return User(username="admin", groups=["admins"])


def _source_row(**overrides):
    data = {
        "uuid": "source-1",
        "name": "source-1",
        "source_type": "local_fs",
        "path": "/tmp/source-1",
        "watch": True,
        "initial_scan": True,
        "auto_process_new": True,
        "force_polling": True,
        "poll_interval_seconds": 5,
        "watcher_type": "auto",
        "smb_server": None,
        "smb_share": None,
        "smb_port": 445,
        "smb_username": None,
        "smb_password": None,
        "smb_domain": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_sync_watch_tasks_restarts_task_when_force_polling_changes(monkeypatch):
    started: list[tuple] = []
    cancelled: list[str] = []

    async def _fake_watch(folder: LocalFsDataConnector) -> None:
        started.append(
            (folder.uuid, folder.force_polling, folder.poll_interval_seconds)
        )
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.append(folder.uuid)
            raise

    monkeypatch.setattr("services.watcher._watch_folder_dispatch", _fake_watch)

    svc = WatcherService()
    try:
        source_v1 = LocalFsDataConnector(
            uuid="source-1",
            name="source-1",
            path="/tmp/source-1",
            watch=True,
            force_polling=False,
            poll_interval_seconds=3,
        )
        await svc._sync_watch_tasks([source_v1])
        await asyncio.sleep(0)
        first_task = svc._tasks["source-1"]

        source_v2 = LocalFsDataConnector(
            uuid="source-1",
            name="source-1",
            path="/tmp/source-1",
            watch=True,
            force_polling=True,
            poll_interval_seconds=3,
        )
        await svc._sync_watch_tasks([source_v2])
        await asyncio.sleep(0)
        second_task = svc._tasks["source-1"]

        assert second_task is not first_task
        assert first_task.cancelled()
        assert svc._watch_signatures["source-1"] == (
            str(Path("/tmp/source-1").resolve()),
            True,
            3,
            "auto",
            "",
            "",
            445,
        )
        assert started == [("source-1", False, 3), ("source-1", True, 3)]
        assert "source-1" in cancelled
    finally:
        await svc.stop()


def test_create_data_connector_reloads_watcher(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    app.state.watcher.reload_config = AsyncMock()
    try:
        with patch(
            "routers.admin.data_connectors.DataConnectorService.create_connector",
            new=AsyncMock(return_value=_source_row()),
        ):
            response = test_client.post(
                "/api/data-connectors",
                json={
                    "name": "source-1",
                    "connector_type": "local_fs",
                    "path": "/tmp/source-1",
                    "watch": True,
                    "initial_scan": True,
                    "auto_process_new": True,
                    "force_polling": True,
                    "poll_interval_seconds": 5,
                },
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 201
    assert app.state.watcher.reload_config.await_count == 1


def test_update_data_connector_reloads_watcher(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    app.state.watcher.reload_config = AsyncMock()
    try:
        with patch(
            "routers.admin.data_connectors.DataConnectorService.update_connector",
            new=AsyncMock(return_value=_source_row(force_polling=False)),
        ):
            response = test_client.patch(
                "/api/data-connectors/source-1",
                json={"watch": True, "force_polling": False},
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert app.state.watcher.reload_config.await_count == 1


def test_delete_data_connector_reloads_watcher(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    app.state.watcher.stop_connector = AsyncMock()
    app.state.watcher.reload_config = AsyncMock()
    delete_connector = AsyncMock(return_value=True)
    try:
        with patch(
            "routers.admin.data_connectors.DataConnectorService.delete_connector",
            new=delete_connector,
        ):
            response = test_client.delete("/api/data-connectors/source-1")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json() == {"removed": True}
    assert app.state.watcher.reload_config.await_count == 1
    assert app.state.watcher.stop_connector.await_count == 0
    assert delete_connector.await_args.kwargs["force"] is False


def test_delete_data_connector_force_stops_connector_watcher_and_reloads(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    app.state.watcher.stop_connector = AsyncMock()
    app.state.watcher.reload_config = AsyncMock()
    delete_connector = AsyncMock(return_value=True)
    try:
        with patch(
            "routers.admin.data_connectors.DataConnectorService.delete_connector",
            new=delete_connector,
        ):
            response = test_client.delete("/api/data-connectors/source-1?force=true")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert response.json() == {"removed": True}
    assert app.state.watcher.stop_connector.await_count == 1
    assert app.state.watcher.stop_connector.await_args.args[0] == "source-1"
    assert app.state.watcher.reload_config.await_count == 1
    assert delete_connector.await_args.kwargs["force"] is True


@pytest.mark.asyncio
async def test_reload_config_scans_newly_watched_source(monkeypatch):
    folder = LocalFsDataConnector(
        uuid="source-1",
        name="source-1",
        path="/tmp/source-1",
        watch=True,
        initial_scan=True,
        force_polling=True,
        poll_interval_seconds=3,
    )
    svc = WatcherService()
    svc._started = True

    class _DummySession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    refresh_cache = AsyncMock()
    sync_watch_tasks = AsyncMock(return_value={"source-1"})
    scan_existing = AsyncMock()

    async def _refresh_runtime_connectors(_self):
        await refresh_cache()
        return [folder]

    monkeypatch.setattr("services.watcher.AsyncSessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        "services.watcher.ConnectorRuntimeService.refresh",
        _refresh_runtime_connectors,
    )
    monkeypatch.setattr(
        "services.watcher.ConnectorRuntimeService.browsable_connectors",
        lambda _self: [folder],
    )
    monkeypatch.setattr(svc, "_sync_watch_tasks", sync_watch_tasks)
    monkeypatch.setattr("services.watcher._scan_existing", scan_existing)

    try:
        await svc.reload_config()
        await asyncio.sleep(0)

        assert refresh_cache.await_count == 1
        assert sync_watch_tasks.await_count == 1
        assert scan_existing.await_count == 1
        assert scan_existing.await_args.args[0].uuid == "source-1"
        assert svc._scan_signatures["source-1"] == svc._scan_signature(folder)
    finally:
        await svc.stop()


@pytest.mark.asyncio
async def test_stop_cancels_outstanding_initial_scan(monkeypatch):
    cancelled: list[str] = []

    async def _fake_scan(folder: LocalFsDataConnector) -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.append(folder.uuid)
            raise

    monkeypatch.setattr("services.watcher._scan_existing", _fake_scan)

    svc = WatcherService()
    folder = LocalFsDataConnector(
        uuid="source-1",
        name="source-1",
        path="/tmp/source-1",
        initial_scan=True,
        force_polling=True,
        poll_interval_seconds=3,
    )

    svc._start_scan_task("source-1", folder, svc._scan_signature(folder))
    await asyncio.sleep(0)

    await svc.stop()

    assert cancelled == ["source-1"]
    assert svc._scan_tasks == {}
    assert svc._scan_signatures == {}


@pytest.mark.asyncio
async def test_switching_watcher_type_triggers_restart(monkeypatch):
    """Changing watcher_type should cause the watcher task to be restarted."""
    started: list[str] = []
    cancelled: list[str] = []

    async def _fake_watch(folder: LocalFsDataConnector) -> None:
        started.append(folder.watcher_type)
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.append(folder.uuid)
            raise

    monkeypatch.setattr("services.watcher._watch_folder_dispatch", _fake_watch)

    svc = WatcherService()
    try:
        source_v1 = LocalFsDataConnector(
            uuid="source-1",
            name="source-1",
            path="/tmp/source-1",
            watch=True,
            watcher_type="auto",
        )
        await svc._sync_watch_tasks([source_v1])
        await asyncio.sleep(0)

        source_v2 = LocalFsDataConnector(
            uuid="source-1",
            name="source-1",
            path="/tmp/source-1",
            watch=True,
            watcher_type="smb_notify",
            smb_server="fileserver",
            smb_share="docs",
        )
        await svc._sync_watch_tasks([source_v2])
        await asyncio.sleep(0)

        assert started == ["auto", "smb_notify"]
        assert "source-1" in cancelled
    finally:
        await svc.stop()
