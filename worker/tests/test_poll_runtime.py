"""Focused tests for worker poll-loop runtime helpers."""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from models import WorkerClaimedTask
from poll_runtime import (
    HttpJobContext,
    TaskProgress,
    coerce_task,
    compute_backoff_seconds,
    is_fatal_claim_failure,
    is_fatal_processing_failure,
    is_invalid_task_identity_failure,
    report_aborted_result,
    report_completed_result,
    report_processing_failure,
    start_task_heartbeat,
    stop_task_heartbeat,
    upload_extracted_output,
)
from processors import ProcessingResult


def claimed_task() -> WorkerClaimedTask:
    """Build a representative claimed task for helper tests."""
    return WorkerClaimedTask(
        task_id="task-1",
        task_type="process",
        task_secret="secret-1",
        relative_path="example.pdf",
        folder_uuid="folder-1",
        content_item_id="file-1",
    )


def http_error(status_code: int) -> requests.exceptions.HTTPError:
    """Build an HTTPError with a specific response status."""
    error = requests.exceptions.HTTPError(f"HTTP {status_code}")
    response = requests.Response()
    response.status_code = status_code
    error.response = response
    return error


def test_compute_backoff_seconds_uses_exponential_delay_with_jitter():
    with patch("poll_runtime.random.uniform", return_value=0.75) as mock_uniform:
        delay = compute_backoff_seconds(5.0, 3)

    assert delay == 20.75
    mock_uniform.assert_called_once_with(0, 1.0)


def test_is_fatal_claim_failure_treats_validation_errors_as_fatal():
    assert is_fatal_claim_failure(ValueError("invalid claim payload")) is True


def test_is_fatal_claim_failure_treats_401_as_fatal():
    assert is_fatal_claim_failure(http_error(401)) is True


def test_is_fatal_processing_failure_treats_missing_or_conflicted_content_as_non_retryable():
    assert is_fatal_processing_failure(http_error(404)) is True
    assert is_fatal_processing_failure(http_error(409)) is True
    assert is_fatal_processing_failure(http_error(500)) is False


def test_invalid_task_identity_failures_are_stop_signals():
    assert is_invalid_task_identity_failure(http_error(401)) is True
    assert is_invalid_task_identity_failure(http_error(403)) is True
    assert is_invalid_task_identity_failure(http_error(404)) is True
    assert is_invalid_task_identity_failure(http_error(409)) is True
    assert is_invalid_task_identity_failure(http_error(500)) is False
    assert is_invalid_task_identity_failure(Exception("network")) is False


def test_coerce_task_normalizes_dict_payloads():
    task = coerce_task(
        {
            "task_id": "task-1",
            "task_type": "process",
            "task_secret": "secret-1",
            "relative_path": "example.pdf",
            "folder_uuid": "folder-1",
            "content_item_id": "file-1",
        }
    )

    assert isinstance(task, WorkerClaimedTask)
    assert task.task_id == "task-1"


def test_report_completed_result_forwards_processing_metadata():
    client = MagicMock()
    task = claimed_task()
    result = ProcessingResult(
        status="completed",
        file_path="example.pdf",
        message="done",
        metadata={
            "processing_config": {"do_ocr": False},
            "document_classification": {"label": "invoice"},
            "document_extraction": {"schema_name": "invoice"},
        },
    )

    report_completed_result(client, task, result)

    client.complete_task.assert_called_once_with(
        "task-1",
        "secret-1",
        processing_config={"do_ocr": False},
        document_classification={"label": "invoice"},
        document_extraction={"schema_name": "invoice"},
    )


def test_report_aborted_result_ignores_invalid_task_identity():
    client = MagicMock()
    client.abort_task.side_effect = http_error(404)
    result = ProcessingResult(
        status="aborted",
        file_path="example.pdf",
        message="Superseded before saving results",
        aborted=True,
    )

    report_aborted_result(client, claimed_task(), result)

    client.abort_task.assert_called_once_with(
        "task-1",
        "secret-1",
        reason="Superseded before saving results",
    )


def test_report_aborted_result_reraises_unexpected_errors():
    client = MagicMock()
    client.abort_task.side_effect = http_error(500)
    result = ProcessingResult(
        status="aborted",
        file_path="example.pdf",
        message="Superseded before saving results",
        aborted=True,
    )

    with pytest.raises(requests.exceptions.HTTPError):
        report_aborted_result(client, claimed_task(), result)


def test_report_processing_failure_aborts_superseded_tasks():
    client = MagicMock()
    log = MagicMock()

    report_processing_failure(
        client, claimed_task(), Exception("Superseded during processing"), log
    )

    client.abort_task.assert_called_once_with(
        "task-1",
        "secret-1",
        reason="Superseded during processing",
    )
    client.fail_task.assert_not_called()


def test_report_processing_failure_marks_fatal_http_errors_non_retryable():
    client = MagicMock()
    log = MagicMock()

    report_processing_failure(client, claimed_task(), http_error(404), log)

    client.fail_task.assert_called_once_with(
        "task-1",
        "secret-1",
        "FATAL: non-retryable upstream error (404): HTTP 404",
    )
    client.abort_task.assert_not_called()


def test_upload_extracted_output_sends_task_id_and_secret(tmp_path):
    client = MagicMock()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    task = claimed_task()

    upload_extracted_output(
        client,
        content_item_id="file-1",
        output_dir=output_dir,
        task=task,
        log=MagicMock(),
    )

    client.upload_extracted_directory.assert_called_once_with(
        "file-1",
        output_dir,
        "task-1",
        "secret-1",
    )


def test_task_progress_set_and_get_is_thread_safe_holder():
    progress = TaskProgress()
    assert progress.get() is None
    progress.set("converting")
    assert progress.get() == "converting"
    progress.set(None)
    assert progress.get() is None


def test_http_job_context_set_stage_writes_to_progress_holder():
    progress = TaskProgress()
    job_ctx = HttpJobContext(
        task_id="task-1",
        task_secret="secret-1",
        correlation_id="corr-1",
        _client=MagicMock(),
        progress=progress,
    )
    job_ctx.set_stage("chunking")
    assert progress.get() == "chunking"


def test_http_job_context_set_stage_without_progress_is_noop():
    job_ctx = HttpJobContext(
        task_id="task-1",
        task_secret="secret-1",
        correlation_id="corr-1",
        _client=MagicMock(),
    )
    # Should not raise when no progress holder is attached.
    job_ctx.set_stage("chunking")


def test_start_task_heartbeat_forwards_current_stage():
    progress = TaskProgress()
    progress.set("embedding")
    client = MagicMock()

    heartbeat = start_task_heartbeat(
        "task-1",
        "secret-1",
        0.01,
        progress=progress,
        backend_client_factory=lambda: client,
    )
    try:
        # Allow at least one heartbeat tick to fire.
        for _ in range(200):
            if client.heartbeat_task.call_count:
                break
            time.sleep(0.01)
    finally:
        stop_task_heartbeat(heartbeat)

    assert client.heartbeat_task.call_count >= 1
    _, kwargs = client.heartbeat_task.call_args
    assert kwargs.get("stage") == "embedding"
