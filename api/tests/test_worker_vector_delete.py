"""Tests for worker vector delete endpoint behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from auth.worker_auth import require_worker_token
from database import get_db

_TASK_SECRET = "test-task-secret"
_TASK_SECRET_HEADER = {"X-Task-Secret": _TASK_SECRET}


def test_vector_delete_with_folder_uuid_uses_deterministic_file_id(test_client):
    from main import app

    mock_db = AsyncMock()
    expected_file_id = "cafebabe1234abcd"
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ) as mock_get_folder,
            patch(
                "routers.worker.proxy.compute_content_item_id",
                return_value=expected_file_id,
            ) as mock_compute_content_item_id,
            patch(
                "routers.worker.proxy.VectorService.delete_chunks",
                new=AsyncMock(return_value=7),
            ) as mock_delete_chunks,
            patch(
                "routers.worker.proxy.authorize_task_request",
                new_callable=AsyncMock,
            ) as mock_authorize_task_request,
        ):
            response = test_client.post(
                "/api/worker/vector/delete",
                json={
                    "folder_uuid": "folder-1",
                    "file_path": "docs/report.txt",
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "deleted": 7}
    mock_get_folder.assert_awaited_once_with("folder-1", mock_db)
    mock_compute_content_item_id.assert_called_once_with("folder-1", "docs/report.txt")
    mock_authorize_task_request.assert_awaited_once()
    assert mock_authorize_task_request.await_args.kwargs["worker_id"] == "worker-1"
    mock_delete_chunks.assert_awaited_once_with(mock_db, expected_file_id, None)


def test_vector_delete_prefers_request_content_item_id(test_client):
    from main import app

    mock_db = AsyncMock()
    app.dependency_overrides[require_worker_token] = lambda: "worker-1"

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "routers.worker.proxy.get_folder",
                new=AsyncMock(return_value=SimpleNamespace(uuid="folder-1")),
            ) as mock_get_folder,
            patch(
                "routers.worker.proxy.compute_content_item_id",
                side_effect=AssertionError("path fallback should not be used"),
            ),
            patch(
                "routers.worker.proxy.VectorService.delete_chunks",
                new=AsyncMock(return_value=4),
            ) as mock_delete_chunks,
            patch(
                "routers.worker.proxy.authorize_task_request",
                new_callable=AsyncMock,
            ) as mock_authorize_task_request,
        ):
            response = test_client.post(
                "/api/worker/vector/delete",
                json={
                    "folder_uuid": "folder-1",
                    "file_path": "worker/display/path.txt",
                    "content_item_id": "23bfe864fab4c490",
                    "exclude_version": "v1",
                },
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "deleted": 4}
    mock_get_folder.assert_awaited_once_with("folder-1", mock_db)
    mock_authorize_task_request.assert_awaited_once()
    assert mock_authorize_task_request.await_args.kwargs["worker_id"] == "worker-1"
    assert mock_authorize_task_request.await_args.kwargs["content_item_id"] == (
        "23bfe864fab4c490"
    )
    mock_delete_chunks.assert_awaited_once_with(mock_db, "23bfe864fab4c490", "v1")


def test_vector_delete_requires_folder_uuid(test_client):
    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        response = test_client.post(
            "/api/worker/vector/delete",
            json={"file_path": "shared/path.txt"},
            headers=_TASK_SECRET_HEADER,
        )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 422
