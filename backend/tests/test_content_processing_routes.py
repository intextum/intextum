"""Tests for file processing route ownership propagation."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from models.enums import ProcessingStatus
from models.sqlalchemy_models import IndexedContentItem
from routers.content.processing import (
    MISSING_TASK_ABORT_MESSAGE,
    _batch_process_response,
    _enqueue_relative_path,
    _mark_missing_task_aborted,
    _ok_response,
)


def test_batch_process_response_adds_optional_matched_count():
    tasks = [{"task_id": "task-123"}]

    assert _batch_process_response(tasks, errors=1, matched=5) == {
        "message": "Queued 1 file(s) for processing",
        "queued": 1,
        "errors": 1,
        "tasks": tasks,
        "matched": 5,
    }


def test_ok_response_adds_optional_message():
    assert _ok_response() == {"status": "ok"}
    assert _ok_response(message="done") == {"status": "ok", "message": "done"}


def test_mark_missing_task_aborted_revokes_record_and_clears_task_credentials():
    record = IndexedContentItem(
        content_item_id="file-1",
        processing_status=ProcessingStatus.PROCESSING,
        task_id="task-1",
        task_secret="secret-1",
    )

    _mark_missing_task_aborted(record)

    assert record.processing_status == ProcessingStatus.REVOKED
    assert record.error_message == MISSING_TASK_ABORT_MESSAGE
    assert record.task_id is None
    assert record.task_secret is None


@pytest.mark.asyncio
async def test_enqueue_relative_path_logs_enqueue_exception(caplog):
    with patch(
        "routers.content.processing.enqueue_single_file",
        new=AsyncMock(side_effect=RuntimeError("queue unavailable")),
    ):
        result, errors = await _enqueue_relative_path(
            object(),
            "reports/file.pdf",
            AsyncMock(),
        )

    assert result is None
    assert errors == 1
    assert "Failed to enqueue content processing for reports/file.pdf" in caplog.text


def test_trigger_process_passes_requested_by_sub_to_enqueue_single_file(test_client):
    folder = object()
    enqueue_single_file = AsyncMock(return_value={"task_id": "task-123"})

    with (
        patch(
            "routers.content.processing.resolve_authorized_source_file",
            new=AsyncMock(return_value=(folder, "file1.pdf")),
        ),
        patch(
            "routers.content.processing.enqueue_single_file",
            new=enqueue_single_file,
        ),
    ):
        response = test_client.post(
            "/api/content/process",
            params={"path": "documents/file1.pdf"},
            json={"processing_config": {"ocr": True}},
        )

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-123"
    assert enqueue_single_file.await_args.args[:2] == (folder, "file1.pdf")
    assert enqueue_single_file.await_args.kwargs == {
        "processing_config": {"ocr": True},
        "requested_by_sub": "sub-testuser",
    }


def test_trigger_batch_process_directory_passes_requested_by_sub(test_client):
    folder = object()
    enqueue_paths = AsyncMock(return_value=([{"task_id": "task-123"}], 1))

    with (
        patch(
            "routers.content.processing.resolve_authorized_source_dir",
            new=AsyncMock(return_value=(folder, "reports")),
        ),
        patch(
            "routers.content.processing._enqueue_paths_in_directory",
            new=enqueue_paths,
        ),
    ):
        response = test_client.post(
            "/api/content/process-batch",
            json={
                "directory_path": "documents/reports",
                "processing_config": {"enrichment_only": True},
            },
        )

    assert response.status_code == 200
    assert response.json()["queued"] == 1
    assert response.json()["errors"] == 1
    assert enqueue_paths.await_args.args[:2] == (folder, "reports")
    assert enqueue_paths.await_args.kwargs == {
        "processing_config": {"enrichment_only": True},
        "requested_by_sub": "sub-testuser",
    }


def test_trigger_batch_process_paths_passes_requested_by_sub(test_client):
    enqueue_paths = AsyncMock(return_value=([{"task_id": "task-123"}], 0))
    paths = ["documents/file1.pdf", "images/image1.jpg"]

    with patch(
        "routers.content.processing._enqueue_explicit_paths",
        new=enqueue_paths,
    ):
        response = test_client.post(
            "/api/content/process-batch",
            json={"paths": paths, "processing_config": {"document_enrichment": True}},
        )

    assert response.status_code == 200
    assert response.json()["queued"] == 1
    assert response.json()["errors"] == 0
    assert enqueue_paths.await_args.args[0] == paths
    assert enqueue_paths.await_args.args[1].sub == "sub-testuser"
    assert enqueue_paths.await_args.kwargs == {
        "processing_config": {"document_enrichment": True},
        "requested_by_sub": "sub-testuser",
    }


def test_trigger_filtered_batch_process_passes_filters_and_requested_by_sub(
    test_client,
):
    matching_paths = ["documents/file1.pdf", "documents/file2.pdf"]
    list_matching_paths = AsyncMock(return_value=matching_paths)
    enqueue_paths = AsyncMock(return_value=([{"task_id": "task-123"}], 0))

    with (
        patch(
            "routers.content.processing.ContentStatsService.list_all_matching_paths",
            new=list_matching_paths,
        ),
        patch(
            "routers.content.processing._enqueue_explicit_paths",
            new=enqueue_paths,
        ),
    ):
        response = test_client.post(
            "/api/content/process-batch-filtered",
            json={
                "name": "Approval.*",
                "name_regex": True,
                "search_path": True,
                "content_kind": "email_message",
                "document_class": "Invoice",
                "extraction_field": "invoice_number",
                "extraction_value": "RE-2026",
                "extraction_value_number_min": 10.5,
                "extraction_value_number_max": 20.0,
                "extraction_value_date_from": "2026-04-01",
                "extraction_value_date_to": "2026-04-30",
                "stale_enrichment": True,
                "processing_config": {
                    "enrichment_only": True,
                    "document_enrichment": True,
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["queued"] == 1
    assert response.json()["errors"] == 0
    assert response.json()["matched"] == 2
    assert list_matching_paths.await_args.kwargs == {
        "user": enqueue_paths.await_args.args[1],
        "name_contains": "Approval.*",
        "name_regex": True,
        "search_path": True,
        "path": None,
        "content_kind": "email_message",
        "extension": None,
        "status": None,
        "document_class": "Invoice",
        "extraction_schema": None,
        "extraction_field": "invoice_number",
        "extraction_value": "RE-2026",
        "extraction_value_number_min": 10.5,
        "extraction_value_number_max": 20.0,
        "extraction_value_date_from": date(2026, 4, 1),
        "extraction_value_date_to": date(2026, 4, 30),
        "field_predicates": (),
        "review_status": None,
        "review_reason": None,
        "needs_review": False,
        "stale_enrichment": True,
    }
    assert enqueue_paths.await_args.args[0] == matching_paths
    assert enqueue_paths.await_args.args[1].sub == "sub-testuser"
    assert enqueue_paths.await_args.kwargs == {
        "processing_config": {
            "enrichment_only": True,
            "document_enrichment": True,
        },
        "requested_by_sub": "sub-testuser",
    }
