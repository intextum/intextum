"""Security tests for worker helper auth guards."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from routers.worker.helpers import (
    authorize_extracted_upload,
    authorize_claimed_process_task_request,
    authorize_task_request_for_content_item_ids,
    build_worker_file_ref,
    get_task_id_header,
    get_task_secret_header,
    parse_batch_sub_paths,
    require_task_access,
)


def _request_with_headers(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in headers.items()
        ],
    }
    return Request(scope)


def _db_with_active_task_secrets(secrets_list: list[str]) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = [
        MagicMock(id=f"task-{idx}", content_item_id="file-1", task_secret=secret)
        for idx, secret in enumerate(secrets_list, start=1)
    ]
    result.scalars.return_value = scalars_result
    db.execute.return_value = result
    return db


def test_get_task_secret_header_rejects_missing_header():
    request = _request_with_headers({})

    with pytest.raises(HTTPException) as exc_info:
        get_task_secret_header(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing X-Task-Secret header"


def test_get_task_secret_header_returns_header_value():
    request = _request_with_headers({"x-task-secret": "secret-123"})

    assert get_task_secret_header(request) == "secret-123"


def test_get_task_id_header_rejects_missing_header():
    request = _request_with_headers({})

    with pytest.raises(HTTPException) as exc_info:
        get_task_id_header(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing X-Task-Id header"


def test_get_task_id_header_returns_header_value():
    request = _request_with_headers({"x-task-id": "task-123"})

    assert get_task_id_header(request) == "task-123"


@pytest.mark.asyncio
async def test_require_task_access_allows_matching_claimed_secret():
    db = _db_with_active_task_secrets(["secret-a", "secret-b"])

    await require_task_access("file-1", "secret-b", db)

    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_require_task_access_rejects_non_matching_secret():
    db = _db_with_active_task_secrets(["secret-a", "secret-b"])

    with pytest.raises(HTTPException) as exc_info:
        await require_task_access("file-1", "wrong-secret", db)

    assert exc_info.value.status_code == 403
    assert "does not match any active task" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_task_access_rejects_when_no_claimed_tasks():
    db = _db_with_active_task_secrets([])

    with pytest.raises(HTTPException) as exc_info:
        await require_task_access("file-1", "secret-a", db)

    assert exc_info.value.status_code == 403
    assert "does not match any active task" in exc_info.value.detail


def test_build_worker_file_ref_normalizes_relative_path():
    file_ref = build_worker_file_ref("folder-1", "/nested/report.pdf/")

    assert file_ref.folder_uuid == "folder-1"
    assert file_ref.relative_path == "nested/report.pdf"
    assert file_ref.content_item_id


def test_parse_batch_sub_paths_trims_slashes_and_rejects_empty_values():
    assert parse_batch_sub_paths('["/a.txt/","nested/b.txt"]', 2) == [
        "a.txt",
        "nested/b.txt",
    ]

    with pytest.raises(HTTPException) as exc_info:
        parse_batch_sub_paths('[""]', 1)

    assert exc_info.value.status_code == 400
    assert "non-empty string" in exc_info.value.detail


@pytest.mark.asyncio
async def test_authorize_task_request_for_content_item_ids_reuses_single_header():
    request = _request_with_headers({"x-task-secret": "secret-123"})
    db = AsyncMock()

    with patch(
        "routers.worker.helpers.require_task_access", new_callable=AsyncMock
    ) as mock_require:
        task_secret = await authorize_task_request_for_content_item_ids(
            request,
            content_item_ids=["file-1", "file-2"],
            db=db,
            worker_id="worker-1",
        )

    assert task_secret == "secret-123"
    assert mock_require.await_args_list == [
        call("file-1", "secret-123", db, worker_id="worker-1"),
        call("file-2", "secret-123", db, worker_id="worker-1"),
    ]


@pytest.mark.asyncio
async def test_authorize_claimed_process_task_request_returns_task_binding():
    request = _request_with_headers(
        {"x-task-id": "task-123", "x-task-secret": "secret-123"}
    )
    db = AsyncMock()
    task = MagicMock()
    task.status = "CLAIMED"
    task.task_type = "process"
    task.content_item_id = "a1b2c3"
    task.folder_uuid = "folder-1"
    task.relative_path = "docs/report.pdf"

    with patch("routers.worker.helpers.TaskQueueService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.get_authorized_task = AsyncMock(return_value=task)

        binding = await authorize_claimed_process_task_request(
            request, db=db, worker_id="worker-1"
        )

    mock_service_cls.assert_called_once_with(db)
    mock_service.get_authorized_task.assert_awaited_once_with(
        "task-123", "secret-123", worker_id="worker-1"
    )
    assert binding.task_secret == "secret-123"
    assert binding.task_id == "task-123"
    assert binding.content_item_id == "a1b2c3"
    assert binding.folder_uuid == "folder-1"
    assert binding.relative_path == "docs/report.pdf"


@pytest.mark.asyncio
async def test_authorize_claimed_process_task_request_rejects_missing_task():
    request = _request_with_headers(
        {"x-task-id": "task-123", "x-task-secret": "secret-123"}
    )
    db = AsyncMock()

    with patch("routers.worker.helpers.TaskQueueService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.get_authorized_task = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await authorize_claimed_process_task_request(
                request, db=db, worker_id="worker-1"
            )

    assert exc_info.value.status_code == 403
    assert "active processing task" in exc_info.value.detail


@pytest.mark.asyncio
async def test_authorize_claimed_process_task_request_passes_worker_id_to_auth():
    request = _request_with_headers(
        {"x-task-id": "task-123", "x-task-secret": "secret-123"}
    )
    db = AsyncMock()

    with patch("routers.worker.helpers.TaskQueueService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.get_authorized_task = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await authorize_claimed_process_task_request(
                request, db=db, worker_id="wrong-worker"
            )

    assert exc_info.value.status_code == 403
    mock_service.get_authorized_task.assert_awaited_once_with(
        "task-123", "secret-123", worker_id="wrong-worker"
    )


@pytest.mark.asyncio
async def test_authorize_claimed_process_task_request_rejects_inactive_task():
    request = _request_with_headers(
        {"x-task-id": "task-123", "x-task-secret": "secret-123"}
    )
    db = AsyncMock()
    task = MagicMock()
    task.status = "COMPLETED"
    task.task_type = "process"
    task.content_item_id = "a1b2c3"

    with patch("routers.worker.helpers.TaskQueueService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.get_authorized_task = AsyncMock(return_value=task)

        with pytest.raises(HTTPException) as exc_info:
            await authorize_claimed_process_task_request(
                request, db=db, worker_id="worker-1"
            )

    assert exc_info.value.status_code == 409
    assert "no longer active" in exc_info.value.detail


@pytest.mark.asyncio
async def test_authorize_extracted_upload_requires_task_id_header():
    request = _request_with_headers({"x-task-secret": "secret-123"})
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await authorize_extracted_upload(
            request, content_item_id="a1b2c3", db=db, worker_id="worker-1"
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing X-Task-Id header"


@pytest.mark.asyncio
async def test_authorize_extracted_upload_rejects_content_item_mismatch():
    request = _request_with_headers(
        {"x-task-id": "task-123", "x-task-secret": "secret-123"}
    )
    db = AsyncMock()
    task = MagicMock()
    task.status = "CLAIMED"
    task.task_type = "process"
    task.content_item_id = "file-1"
    task.folder_uuid = "folder-1"
    task.relative_path = "docs/report.pdf"

    with patch("routers.worker.helpers.TaskQueueService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.get_authorized_task = AsyncMock(return_value=task)

        with pytest.raises(HTTPException) as exc_info:
            await authorize_extracted_upload(
                request,
                content_item_id="deadbeef",
                db=db,
                worker_id="worker-1",
            )

    assert exc_info.value.status_code == 409
    assert "does not match upload content item" in exc_info.value.detail
