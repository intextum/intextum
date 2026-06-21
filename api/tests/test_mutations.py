"""Tests for file mutation endpoints (upload, mkdir, delete)."""

import logging
from types import SimpleNamespace
import pytest
from unittest.mock import patch, AsyncMock

from routers.content.mutations import _child_relative_path, _ok_response
from services.adapters.base import ContentEntry, DataConnectorWriteTooLargeError


@pytest.fixture(autouse=True)
def _bypass_acl():
    """Disable ACL checks for mutation tests."""

    async def _noop(*args, **kwargs):
        pass

    with patch("services.content.access._ensure_folder_acl", new=_noop):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    name: str,
    rel: str,
    *,
    is_dir: bool = False,
    is_file: bool = False,
    size: int = 0,
) -> ContentEntry:
    return ContentEntry(
        name=name,
        relative_path=rel,
        is_dir=is_dir,
        is_file=is_file,
        is_symlink=False,
        size_bytes=size,
        modified_time=1700000000.0,
        change_time=1700000000.0,
    )


def test_child_relative_path_joins_optional_parent():
    assert _child_relative_path("", "report.pdf") == "report.pdf"
    assert _child_relative_path("invoices/2026", "report.pdf") == (
        "invoices/2026/report.pdf"
    )


def test_ok_response_adds_payload_fields():
    assert _ok_response(path="report.pdf", size=5) == {
        "status": "ok",
        "path": "report.pdf",
        "size": 5,
    }


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUpload:
    def test_upload_file(self, test_client, populated_data_dir):
        """Upload a new file into the documents folder."""
        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "documents"},
            files={"file": ("newfile.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["path"] == "newfile.txt"
        assert body["size"] > 0
        # File should exist on disk
        assert (populated_data_dir / "documents" / "newfile.txt").exists()

    def test_upload_into_subdir(self, test_client, populated_data_dir):
        """Upload into a subdirectory."""
        subdir = populated_data_dir / "documents" / "subdir"
        subdir.mkdir()

        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "documents/subdir"},
            files={"file": ("report.pdf", b"%PDF-content", "application/pdf")},
        )
        assert resp.status_code == 200
        assert resp.json()["path"] == "subdir/report.pdf"
        assert (subdir / "report.pdf").exists()

    def test_upload_rejects_hidden_filename(self, test_client):
        """Hidden filenames should be rejected."""
        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "documents"},
            files={"file": (".secret", b"data", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Invalid filename" in resp.json()["detail"]

    def test_upload_rejects_duplicate(self, test_client):
        """Uploading over an existing file should return 409."""
        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "documents"},
            files={"file": ("file1.pdf", b"overwrite", "application/pdf")},
        )
        assert resp.status_code == 409

    def test_upload_unknown_folder(self, test_client):
        """Uploading to an unknown folder should 404."""
        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "nonexistent"},
            files={"file": ("test.txt", b"data", "text/plain")},
        )
        assert resp.status_code == 404

    def test_upload_rejects_path_traversal(self, test_client):
        """Path traversal in filename should be rejected (starts with '.')."""
        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "documents"},
            files={"file": ("../../etc/passwd", b"nope", "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_auto_process_passes_requested_by_sub(self, test_client):
        """Auto-processed uploads should remember which user queued the work."""
        task_service = SimpleNamespace(
            enqueue_process=AsyncMock(return_value="task-123")
        )

        with patch(
            "routers.content.mutations.TaskQueueService", return_value=task_service
        ):
            resp = test_client.post(
                "/api/content/upload",
                params={"directory": "documents"},
                files={"file": ("notify.txt", b"hello world", "text/plain")},
            )

        assert resp.status_code == 200
        assert resp.json()["task_id"] == "task-123"
        payload = task_service.enqueue_process.await_args.args[0]
        assert payload.content_item_id
        assert payload.folder_uuid == "folder-documents"
        assert payload.relative_path == "notify.txt"
        assert payload.requested_by_sub == "sub-testuser"
        assert payload.metadata.source_name == "documents"

    def test_upload_auto_process_failure_logs_traceback(self, test_client, caplog):
        """Auto-process enqueue failures should leave upload successful but diagnosable."""
        task_service = SimpleNamespace(
            enqueue_process=AsyncMock(side_effect=RuntimeError("queue unavailable"))
        )
        caplog.set_level(logging.ERROR, logger="routers.content.mutations")

        with patch(
            "routers.content.mutations.TaskQueueService", return_value=task_service
        ):
            resp = test_client.post(
                "/api/content/upload",
                params={"directory": "documents"},
                files={"file": ("warning.txt", b"hello world", "text/plain")},
            )

        assert resp.status_code == 200
        assert resp.json()["warning"] == (
            "File uploaded but automatic processing could not be started."
        )
        assert "Failed to enqueue uploaded file" in caplog.text
        assert "RuntimeError: queue unavailable" in caplog.text

    def test_upload_rejects_oversized_payload_without_partial_file(
        self, test_client, populated_data_dir
    ):
        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "documents"},
            files={"file": ("too-large.bin", b"x" * 1025, "application/octet-stream")},
        )

        assert resp.status_code == 413
        assert "maximum size" in resp.json()["detail"]
        assert not (populated_data_dir / "documents" / "too-large.bin").exists()


# ---------------------------------------------------------------------------
# Mkdir
# ---------------------------------------------------------------------------


class TestMkdir:
    def test_create_directory(self, test_client, populated_data_dir):
        """Create a new subdirectory."""
        resp = test_client.post(
            "/api/content/mkdir",
            params={"path": "documents/new_folder"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["path"] == "new_folder"
        assert (populated_data_dir / "documents" / "new_folder").is_dir()

    def test_create_nested_directory(self, test_client, populated_data_dir):
        """Create a directory inside another subdirectory."""
        subdir = populated_data_dir / "documents" / "parent"
        subdir.mkdir()

        resp = test_client.post(
            "/api/content/mkdir",
            params={"path": "documents/parent/child"},
        )
        assert resp.status_code == 200
        assert (subdir / "child").is_dir()

    def test_mkdir_rejects_hidden_name(self, test_client):
        """Hidden directory names should be rejected."""
        resp = test_client.post(
            "/api/content/mkdir",
            params={"path": "documents/.hidden_dir"},
        )
        assert resp.status_code == 400
        assert "Invalid directory name" in resp.json()["detail"]

    def test_mkdir_rejects_top_level(self, test_client):
        """Cannot create a top-level folder (must be inside a source)."""
        resp = test_client.post(
            "/api/content/mkdir",
            params={"path": "new_source"},
        )
        assert resp.status_code == 400
        assert "top-level" in resp.json()["detail"]

    def test_mkdir_rejects_duplicate(self, test_client, populated_data_dir):
        """Creating a directory that already exists should 409."""
        subdir = populated_data_dir / "documents" / "existing"
        subdir.mkdir()

        resp = test_client.post(
            "/api/content/mkdir",
            params={"path": "documents/existing"},
        )
        assert resp.status_code == 409

    def test_mkdir_unknown_folder(self, test_client):
        """Mkdir in an unknown folder should 404."""
        resp = test_client.post(
            "/api/content/mkdir",
            params={"path": "nonexistent/newdir"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_file(self, test_client, populated_data_dir):
        """Delete an existing file."""
        target = populated_data_dir / "documents" / "file1.pdf"
        assert target.exists()

        resp = test_client.request(
            "DELETE",
            "/api/content/delete/documents/file1.pdf",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["path"] == "file1.pdf"
        assert not target.exists()

    def test_delete_nonexistent_file(self, test_client):
        """Deleting a nonexistent file should 404."""
        resp = test_client.request(
            "DELETE",
            "/api/content/delete/documents/no_such_file.txt",
        )
        assert resp.status_code == 404

    def test_delete_unknown_folder(self, test_client):
        """Deleting from unknown folder should 404."""
        resp = test_client.request(
            "DELETE",
            "/api/content/delete/nonexistent/file.txt",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Adapter integration (mock adapter to verify adapter-agnostic behaviour)
# ---------------------------------------------------------------------------


class TestAdapterIntegration:
    """Verify that mutation endpoints go through the adapter interface."""

    def test_upload_calls_adapter_write(self, test_client, monkeypatch):
        """Upload should call adapter.write_file and adapter.stat."""
        mock_adapter = AsyncMock()
        mock_adapter.is_dir.return_value = True
        # Root dir exists, but target file does not
        mock_adapter.exists.side_effect = lambda p: p == ""
        mock_adapter.write_file.return_value = 42
        mock_adapter.stat.return_value = _make_entry(
            "test.txt", "test.txt", is_file=True, size=42
        )

        def _get_adapter(self):
            return mock_adapter

        from config import LocalFsDataConnector

        monkeypatch.setattr(LocalFsDataConnector, "get_adapter", _get_adapter)

        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "documents"},
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        assert resp.status_code == 200
        mock_adapter.write_file.assert_awaited_once()
        assert mock_adapter.write_file.await_args.kwargs["max_bytes"] == 1024
        mock_adapter.stat.assert_awaited_once()

    def test_upload_maps_adapter_size_limit_to_413(self, test_client, monkeypatch):
        """Adapter-level size enforcement should return 413 and cleanup target."""
        mock_adapter = AsyncMock()
        mock_adapter.is_dir.return_value = True
        mock_adapter.exists.side_effect = lambda p: p == ""
        mock_adapter.write_file.side_effect = DataConnectorWriteTooLargeError(1024)

        def _get_adapter(self):
            return mock_adapter

        from config import LocalFsDataConnector

        monkeypatch.setattr(LocalFsDataConnector, "get_adapter", _get_adapter)

        resp = test_client.post(
            "/api/content/upload",
            params={"directory": "documents"},
            files={"file": ("test.txt", b"content", "text/plain")},
        )

        assert resp.status_code == 413
        mock_adapter.delete.assert_awaited_once_with("test.txt")

    def test_mkdir_calls_adapter_create_directory(self, test_client, monkeypatch):
        """Mkdir should call adapter.create_directory."""
        mock_adapter = AsyncMock()
        mock_adapter.is_dir.return_value = True
        # Parent dir exists, new dir does not
        mock_adapter.exists.side_effect = lambda p: p == ""

        def _get_adapter(self):
            return mock_adapter

        from config import LocalFsDataConnector

        monkeypatch.setattr(LocalFsDataConnector, "get_adapter", _get_adapter)

        resp = test_client.post(
            "/api/content/mkdir",
            params={"path": "documents/newdir"},
        )
        assert resp.status_code == 200
        mock_adapter.create_directory.assert_awaited_once()

    def test_delete_calls_adapter_delete(self, test_client, monkeypatch):
        """Delete should call adapter.delete."""
        mock_adapter = AsyncMock()
        mock_adapter.exists.return_value = True
        mock_adapter.is_file.return_value = True

        def _get_adapter(self):
            return mock_adapter

        from config import LocalFsDataConnector

        monkeypatch.setattr(LocalFsDataConnector, "get_adapter", _get_adapter)

        resp = test_client.request(
            "DELETE",
            "/api/content/delete/documents/file1.pdf",
        )
        assert resp.status_code == 200
        mock_adapter.delete.assert_awaited_once()
