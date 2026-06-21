"""Security tests for worker file metadata access."""

from unittest.mock import ANY, AsyncMock, patch

from auth.worker_auth import require_worker_token
from routers.worker.content import _source_file_metadata
from services.adapters.base import ContentEntry
from services.utils import compute_content_item_id


def test_source_file_metadata_shapes_adapter_stat_entry():
    entry = ContentEntry(
        name="Report.PDF",
        relative_path="docs/Report.PDF",
        is_dir=False,
        is_file=True,
        is_symlink=False,
        size_bytes=123,
        modified_time=10.5,
        change_time=11.5,
    )

    assert _source_file_metadata(entry) == {
        "size_bytes": 123,
        "modified_time": 10.5,
        "created_time": 11.5,
        "is_symlink": False,
        "file_extension": ".pdf",
    }


def test_worker_file_metadata_requires_task_secret(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        response = test_client.get(
            "/api/worker/file-metadata/folder-documents/file1.pdf"
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing X-Task-Secret header"}


def test_worker_folder_listing_route_is_removed(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        response = test_client.get("/api/worker/folders")
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 404


def test_worker_file_metadata_requires_matching_claimed_task(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        response = test_client.get(
            "/api/worker/file-metadata/folder-documents/file1.pdf",
            headers={"X-Task-Secret": "wrong-secret"},
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 403
    assert "does not match any active task" in response.json()["detail"]


def test_worker_file_metadata_returns_metadata_for_authorized_task(test_client):
    from main import app

    expected_file_id = compute_content_item_id("folder-documents", "file1.pdf")

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch(
                "routers.worker.helpers.require_task_access",
                new=AsyncMock(),
            ) as mock_require_task_access,
            patch(
                "routers.worker.content._collect_source_file_metadata",
                new=AsyncMock(return_value={"size_bytes": 123}),
            ) as mock_collect_metadata,
        ):
            response = test_client.get(
                "/api/worker/file-metadata/folder-documents/file1.pdf",
                headers={"X-Task-Secret": "task-secret"},
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json() == {"size_bytes": 123, "content_item_id": expected_file_id}
    mock_require_task_access.assert_awaited_once_with(
        expected_file_id,
        "task-secret",
        ANY,
        worker_id="worker-1",
    )
    mock_collect_metadata.assert_awaited_once()
