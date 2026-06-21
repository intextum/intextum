"""Tests for worker upload size limits."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from auth.worker_auth import require_worker_token

# Shared task secret used across all upload-limit tests.
_TASK_SECRET = "test-task-secret"
_TASK_ID = "task-1"
_TASK_SECRET_HEADER = {"X-Task-Id": _TASK_ID, "X-Task-Secret": _TASK_SECRET}


def _build_settings(extracted_dir: Path, max_file: int, max_batch: int):
    settings = MagicMock()
    settings.EXTRACTED_DATA_DIR = str(extracted_dir)
    settings.MODEL_ARTIFACTS_DIR = str(extracted_dir.parent / "model-artifacts")
    settings.MAX_UPLOAD_FILE_SIZE_BYTES = max_file
    settings.MAX_UPLOAD_BATCH_SIZE_BYTES = max_batch
    settings.MAX_MODEL_ARTIFACT_UPLOAD_SIZE_BYTES = max_file
    return settings


def _authorized_task(content_item_id: str):
    return MagicMock(
        task_id=_TASK_ID,
        task_secret=_TASK_SECRET,
        content_item_id=content_item_id,
        folder_uuid="folder-1",
        relative_path="docs/file.pdf",
    )


def test_single_upload_rejects_oversized_file(test_client, temp_data_dir):
    extracted_dir = temp_data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    settings = _build_settings(extracted_dir, max_file=8, max_batch=64)
    content_item_id = "a1b2c3"

    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.content.get_settings", return_value=settings),
            patch(
                "routers.worker.content.authorize_extracted_upload",
                new_callable=AsyncMock,
                return_value=_authorized_task(content_item_id),
            ),
        ):
            response = test_client.post(
                f"/api/worker/upload-extracted/{content_item_id}",
                files={"file": ("oversized.txt", b"0123456789", "text/plain")},
                data={"sub_path": "oversized.txt"},
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 413
    assert "max file size" in response.json()["detail"]
    assert not (extracted_dir / content_item_id / "oversized.txt").exists()
    assert not (extracted_dir / ".staging" / _TASK_ID / "oversized.txt").exists()


def test_single_upload_writes_to_task_staging_not_canonical(test_client, temp_data_dir):
    extracted_dir = temp_data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    settings = _build_settings(extracted_dir, max_file=4096, max_batch=4096)
    content_item_id = "a1b2c3"

    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.content.get_settings", return_value=settings),
            patch(
                "routers.worker.content.authorize_extracted_upload",
                new_callable=AsyncMock,
                return_value=_authorized_task(content_item_id),
            ),
        ):
            response = test_client.post(
                f"/api/worker/upload-extracted/{content_item_id}",
                files={"file": ("page-1.txt", b"hello", "text/plain")},
                data={"sub_path": "pages/page-1.txt"},
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "path": f"{content_item_id}/pages/page-1.txt",
        "size": 5,
    }
    assert not (extracted_dir / content_item_id / "pages" / "page-1.txt").exists()
    assert (
        extracted_dir / ".staging" / _TASK_ID / "pages" / "page-1.txt"
    ).read_bytes() == b"hello"


def test_single_upload_rejects_oversized_document_json(test_client, temp_data_dir):
    extracted_dir = temp_data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    settings = _build_settings(extracted_dir, max_file=8, max_batch=64)
    content_item_id = "c0ffee"

    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.content.get_settings", return_value=settings),
            patch(
                "routers.worker.content.authorize_extracted_upload",
                new_callable=AsyncMock,
                return_value=_authorized_task(content_item_id),
            ),
        ):
            response = test_client.post(
                f"/api/worker/upload-extracted/{content_item_id}",
                files={
                    "file": ("document.json", b'{"a":"0123456789"}', "application/json")
                },
                data={"sub_path": "document.json"},
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 413
    assert "max file size" in response.json()["detail"]


def test_batch_upload_rejects_oversized_total(test_client, temp_data_dir):
    extracted_dir = temp_data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    settings = _build_settings(extracted_dir, max_file=64, max_batch=12)
    content_item_id = "deadbeef"

    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.content.get_settings", return_value=settings),
            patch(
                "routers.worker.content.authorize_extracted_upload",
                new_callable=AsyncMock,
                return_value=_authorized_task(content_item_id),
            ),
        ):
            response = test_client.post(
                f"/api/worker/upload-extracted-batch/{content_item_id}",
                files=[
                    ("files", ("first.txt", b"12345678", "text/plain")),
                    ("files", ("second.txt", b"ABCDEFGH", "text/plain")),
                ],
                data={"sub_paths": '["first.txt","second.txt"]'},
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 413
    assert (
        "max batch size" in response.json()["detail"]
        or "max total upload size" in response.json()["detail"]
    )
    assert not (extracted_dir / ".staging" / _TASK_ID / "first.txt").exists()
    assert not (extracted_dir / ".staging" / _TASK_ID / "second.txt").exists()


def test_batch_upload_writes_to_task_staging_and_returns_ok_response(
    test_client, temp_data_dir
):
    extracted_dir = temp_data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    settings = _build_settings(extracted_dir, max_file=64, max_batch=4096)
    content_item_id = "feedface"

    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.content.get_settings", return_value=settings),
            patch(
                "routers.worker.content.authorize_extracted_upload",
                new_callable=AsyncMock,
                return_value=_authorized_task(content_item_id),
            ),
        ):
            response = test_client.post(
                f"/api/worker/upload-extracted-batch/{content_item_id}",
                files=[
                    ("files", ("first.txt", b"alpha", "text/plain")),
                    ("files", ("second.txt", b"bravo!", "text/plain")),
                ],
                data={"sub_paths": '["pages/first.txt","pages/second.txt"]'},
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "content_item_id": content_item_id,
        "uploaded": 2,
        "files": [
            {"path": "pages/first.txt", "size": 5},
            {"path": "pages/second.txt", "size": 6},
        ],
    }
    assert (
        extracted_dir / ".staging" / _TASK_ID / "pages" / "first.txt"
    ).read_bytes() == b"alpha"
    assert (
        extracted_dir / ".staging" / _TASK_ID / "pages" / "second.txt"
    ).read_bytes() == b"bravo!"
    assert not (extracted_dir / content_item_id / "pages" / "first.txt").exists()
    assert not (extracted_dir / content_item_id / "pages" / "second.txt").exists()


def test_batch_upload_rejects_oversized_document_json_file(test_client, temp_data_dir):
    extracted_dir = temp_data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    settings = _build_settings(extracted_dir, max_file=8, max_batch=4096)
    content_item_id = "beadfeed"

    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.content.get_settings", return_value=settings),
            patch(
                "routers.worker.content.authorize_extracted_upload",
                new_callable=AsyncMock,
                return_value=_authorized_task(content_item_id),
            ),
        ):
            response = test_client.post(
                f"/api/worker/upload-extracted-batch/{content_item_id}",
                files=[
                    (
                        "files",
                        ("document.json", b'{"a":"0123456789"}', "application/json"),
                    ),
                ],
                data={"sub_paths": '["document.json"]'},
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 413
    assert "max file size" in response.json()["detail"]


def test_training_artifact_upload_rejects_oversized_file(test_client, temp_data_dir):
    extracted_dir = temp_data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    settings = _build_settings(extracted_dir, max_file=8, max_batch=64)

    from main import app

    app.dependency_overrides[require_worker_token] = lambda: "worker-1"
    try:
        with (
            patch("routers.worker.tasks.get_settings", return_value=settings),
            patch(
                "routers.worker.tasks.ContentEnrichmentTrainingService"
            ) as service_cls,
        ):
            service = service_cls.return_value
            service.get_worker_training_artifact_upload_target = AsyncMock(
                return_value=MagicMock(
                    registry_model_id="model-1",
                    artifact_path="content-enrichment/model-1/adapter.tar.gz",
                    filename="adapter.tar.gz",
                )
            )
            response = test_client.post(
                "/api/worker/tasks/task-1/content-enrichment-training-artifact",
                files={"file": ("adapter.tar.gz", b"0123456789", "application/gzip")},
                headers=_TASK_SECRET_HEADER,
            )
    finally:
        app.dependency_overrides.pop(require_worker_token, None)

    assert response.status_code == 413
    assert "max file size" in response.json()["detail"]
    assert not (
        temp_data_dir
        / "model-artifacts"
        / "content-enrichment"
        / "model-1"
        / "adapter.tar.gz"
    ).exists()
