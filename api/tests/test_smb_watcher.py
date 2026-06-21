"""Unit tests for the SMB CHANGE_NOTIFY watcher."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from watchfiles import Change

from models.connector_types import LocalFsDataConnector
from services.smb_watcher import SmbNotifyWatcher, _SMB_ACTION_MAP


def _smb_folder(**overrides) -> LocalFsDataConnector:
    defaults = {
        "uuid": "smb-1",
        "name": "smb-test",
        "path": "/mnt/share",
        "watch": True,
        "watcher_type": "smb_notify",
        "smb_server": "fileserver",
        "smb_share": "docs",
        "smb_port": 445,
        "smb_username": "user",
        "smb_password": "pass",
    }
    defaults.update(overrides)
    return LocalFsDataConnector(**defaults)


class TestSmbPathToLocal:
    def test_backslash_conversion(self):
        watcher = SmbNotifyWatcher(_smb_folder())
        result = watcher._smb_path_to_local("subdir\\file.txt")
        assert result == "/mnt/share/subdir/file.txt"

    def test_simple_filename(self):
        watcher = SmbNotifyWatcher(_smb_folder())
        result = watcher._smb_path_to_local("readme.md")
        assert result == "/mnt/share/readme.md"

    def test_nested_path(self):
        watcher = SmbNotifyWatcher(_smb_folder(path="/data/mount"))
        result = watcher._smb_path_to_local("a\\b\\c\\d.pdf")
        assert result == "/data/mount/a/b/c/d.pdf"

    def test_already_posix(self):
        watcher = SmbNotifyWatcher(_smb_folder())
        result = watcher._smb_path_to_local("dir/file.txt")
        assert result == "/mnt/share/dir/file.txt"


class TestSmbActionMap:
    def test_added(self):
        assert _SMB_ACTION_MAP[1] == Change.added

    def test_removed(self):
        assert _SMB_ACTION_MAP[2] == Change.deleted

    def test_modified(self):
        assert _SMB_ACTION_MAP[3] == Change.modified

    def test_renamed_old(self):
        assert _SMB_ACTION_MAP[4] == Change.deleted

    def test_renamed_new(self):
        assert _SMB_ACTION_MAP[5] == Change.added


class TestBufferOverflow:
    @pytest.mark.asyncio
    async def test_overflow_yields_empty_batch(self):
        folder = _smb_folder()
        watcher = SmbNotifyWatcher(folder)

        call_count = 0

        def fake_poll():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # buffer overflow
            raise asyncio.CancelledError()

        with (
            patch.object(watcher, "_connect"),
            patch.object(watcher, "_disconnect"),
            patch.object(watcher, "_poll_changes", side_effect=fake_poll),
        ):
            batches = []
            try:
                async for batch in watcher.watch():
                    batches.append(batch)
            except asyncio.CancelledError:
                pass

            assert batches == [[]]


class TestReconnectOnError:
    @pytest.mark.asyncio
    async def test_reconnect_after_connection_error(self):
        folder = _smb_folder(poll_interval_seconds=1)
        watcher = SmbNotifyWatcher(folder)

        connect_count = 0
        disconnect_count = 0

        def fake_connect():
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                raise ConnectionError("connection refused")
            # Second connect succeeds

        def fake_disconnect():
            nonlocal disconnect_count
            disconnect_count += 1

        call_count = 0

        def fake_poll():
            nonlocal call_count
            call_count += 1
            raise asyncio.CancelledError()

        with (
            patch.object(watcher, "_connect", side_effect=fake_connect),
            patch.object(watcher, "_disconnect", side_effect=fake_disconnect),
            patch.object(watcher, "_poll_changes", side_effect=fake_poll),
            patch("services.smb_watcher.asyncio.sleep", new_callable=AsyncMock),
        ):
            try:
                async for _batch in watcher.watch():
                    pass
            except asyncio.CancelledError:
                pass

            assert connect_count == 2
            assert disconnect_count >= 1


class TestDisconnect:
    def test_close_resource_logs_close_failures(self, caplog):
        class BrokenResource:
            def close(self):
                raise OSError("close failed")

        caplog.set_level(logging.DEBUG, logger="services.smb_watcher")

        SmbNotifyWatcher._close_resource(BrokenResource())

        assert "Failed to close SMB watcher resource BrokenResource" in caplog.text
