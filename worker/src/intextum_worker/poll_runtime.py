"""Runtime helpers shared by the worker poll loop."""

from __future__ import annotations

import logging
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from intextum_worker.models import WorkerClaimedTask
from intextum_worker.processors import ProcessingResult
from intextum_worker.services.api_client import ApiClient

logger = logging.getLogger(__name__)

FATAL_HTTP_STATUSES = {400, 401, 403}
FATAL_PROCESS_HTTP_STATUSES = {400, 401, 403, 404, 409}
INVALID_TASK_IDENTITY_HTTP_STATUSES = {401, 403, 404, 409}


def extract_http_status(exc: Exception) -> int | None:
    """Extract an HTTP status code from a request exception when available."""
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code
    return None


def is_fatal_claim_failure(exc: Exception) -> bool:
    """Return True for claim errors that should stop the worker."""
    if isinstance(exc, ValueError):
        return True
    status_code = extract_http_status(exc)
    return status_code in FATAL_HTTP_STATUSES


def is_fatal_processing_failure(exc: Exception) -> bool:
    """Return True for processing errors that should not be retried."""
    status_code = extract_http_status(exc)
    return status_code in FATAL_PROCESS_HTTP_STATUSES


def is_invalid_task_identity_failure(exc: Exception) -> bool:
    """Return True when task-scoped auth says this worker should stop the task."""
    status_code = extract_http_status(exc)
    return status_code in INVALID_TASK_IDENTITY_HTTP_STATUSES


def compute_backoff_seconds(base_seconds: float, failure_count: int) -> float:
    """Compute exponential backoff with bounded jitter."""
    exp_delay = min(60.0, base_seconds * (2 ** max(failure_count - 1, 0)))
    jitter = random.uniform(0, min(1.0, exp_delay * 0.2))
    return exp_delay + jitter


class TaskProgress:
    """Thread-safe holder for the current processing stage of a claimed task.

    The processor writes the active stage at each boundary while the heartbeat
    thread reads it, so stage reporting piggybacks on the existing heartbeat.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stage: str | None = None

    def set(self, stage: str | None) -> None:
        with self._lock:
            self._stage = stage

    def get(self) -> str | None:
        with self._lock:
            return self._stage


def start_task_heartbeat(
    task_id: str,
    task_secret: str,
    interval_seconds: float,
    *,
    progress: TaskProgress | None = None,
    api_client_factory: Callable[[], ApiClient] = ApiClient,
    heartbeat_logger: logging.Logger = logger,
) -> tuple[threading.Event, threading.Thread] | None:
    """Start a background heartbeat loop for a claimed task."""
    try:
        interval = float(interval_seconds)
    except (TypeError, ValueError):
        return None

    if interval <= 0:
        return None

    stop_event = threading.Event()

    def _heartbeat_loop() -> None:
        try:
            client = api_client_factory()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            heartbeat_logger.warning(
                "Failed to start task heartbeat for %s: %s", task_id, exc
            )
            return
        while not stop_event.wait(interval):
            try:
                stage = progress.get() if progress is not None else None
                client.heartbeat_task(task_id, task_secret, stage=stage)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if is_invalid_task_identity_failure(exc):
                    heartbeat_logger.warning(
                        "Task heartbeat stopped for %s because task identity is invalid: %s",
                        task_id,
                        exc,
                    )
                    return
                heartbeat_logger.warning(
                    "Task heartbeat failed for %s: %s", task_id, exc
                )

    thread = threading.Thread(
        target=_heartbeat_loop,
        name=f"task-heartbeat-{task_id[:8]}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def stop_task_heartbeat(
    heartbeat: tuple[threading.Event, threading.Thread] | None,
) -> None:
    """Stop and join a running heartbeat thread."""
    if heartbeat is None:
        return
    stop_event, thread = heartbeat
    stop_event.set()
    thread.join(timeout=2.0)


@dataclass
class HttpJobContext:
    """Job context that checks supersession via HTTP instead of Redis."""

    task_id: str
    task_secret: str
    correlation_id: str
    _client: ApiClient
    progress: TaskProgress | None = None

    def set_stage(self, stage: str) -> None:
        """Record the active processing stage for the heartbeat to report."""
        if self.progress is not None:
            self.progress.set(stage)

    def is_superseded(self) -> bool:
        """Check if this job has been superseded by a newer one."""
        try:
            return self._client.check_superseded(self.task_id, self.task_secret)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if is_invalid_task_identity_failure(exc):
                logger.warning(
                    "Supersession check failed with invalid task identity; aborting task: %s",
                    exc,
                )
                return True
            logger.warning("Supersession check failed: %s", exc)
            return False


def coerce_task(task: WorkerClaimedTask | dict[str, Any]) -> WorkerClaimedTask:
    """Normalize raw claimed-task payloads into a typed worker task."""
    if isinstance(task, WorkerClaimedTask):
        return task
    return WorkerClaimedTask.model_validate(task)


def task_log_extra(task: WorkerClaimedTask) -> dict[str, str]:
    """Common structured log payload for one claimed task."""
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "file_path": task.relative_path,
        "folder_uuid": task.folder_uuid,
    }


def log_result(log: logging.LoggerAdapter, result: ProcessingResult) -> None:
    """Log processing result with an appropriate level."""
    extra = {
        "status": result.status,
        "file_path": result.file_path,
        "chunks_created": result.chunks_created,
        "images_classified": result.images_classified,
        "processing_time_ms": result.processing_time_ms,
    }

    if result.error:
        extra["error"] = result.error
        log.error("Processing failed: %s", result.message, extra=extra)
    elif result.aborted:
        log.info("Processing aborted: %s", result.message, extra=extra)
    else:
        log.info("Processing completed: %s", result.message, extra=extra)


def report_aborted_result(
    client: ApiClient,
    task: WorkerClaimedTask,
    result: ProcessingResult,
) -> None:
    """Report an aborted task result back to the backend."""
    try:
        client.abort_task(
            task.task_id,
            task.task_secret,
            reason=result.message,
        )
    except Exception as exc:
        if is_invalid_task_identity_failure(exc):
            logger.info(
                "Skipping aborted-task report because task identity is already invalid: %s",
                exc,
            )
            return
        raise


def upload_extracted_output(
    client: ApiClient,
    *,
    content_item_id: str | None,
    output_dir,
    task: WorkerClaimedTask,
    log: logging.LoggerAdapter,
) -> None:
    """Upload extracted output files for one completed task."""
    if output_dir is None or not output_dir.exists():
        return
    if not content_item_id:
        return

    upload_result = client.upload_extracted_directory(
        content_item_id,
        output_dir,
        task.task_id,
        task.task_secret,
    )
    log.info(
        "Uploaded %d extracted files to backend",
        upload_result.uploaded,
        extra={
            "content_item_id": upload_result.content_item_id,
            "batch_count": len(upload_result.batches),
        },
    )


def report_completed_result(
    client: ApiClient,
    task: WorkerClaimedTask,
    result: ProcessingResult,
) -> None:
    """Report successful completion for one processed task."""
    processing_config = result.metadata.get("processing_config")
    document_classification = result.metadata.get("document_classification")
    document_extraction = result.metadata.get("document_extraction")
    completion_kwargs: dict[str, object] = {}

    if isinstance(processing_config, dict):
        completion_kwargs["processing_config"] = processing_config
    if document_classification is not None:
        completion_kwargs["document_classification"] = document_classification
    if document_extraction is not None:
        completion_kwargs["document_extraction"] = document_extraction

    client.complete_task(task.task_id, task.task_secret, **completion_kwargs)


def report_processing_failure(
    client: ApiClient,
    task: WorkerClaimedTask,
    exc: Exception,
    log: logging.LoggerAdapter,
) -> None:
    """Map one processing exception to the appropriate backend task update."""
    if "Superseded" in str(exc):
        log.info("Explicitly aborting task in backend due to supersession")
        try:
            client.abort_task(
                task.task_id,
                task.task_secret,
                reason="Superseded during processing",
            )
        except Exception:  # pylint: disable=broad-exception-caught
            log.warning("Failed to report explicit abort to backend")
        return

    if is_fatal_processing_failure(exc):
        status_code = extract_http_status(exc)
        msg = f"FATAL: non-retryable upstream error ({status_code}): {exc}"
        log.error(
            "Processing failed with non-retryable HTTP error",
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "http_status": status_code,
            },
            exc_info=True,
        )
        try:
            client.fail_task(task.task_id, task.task_secret, msg)
        except Exception:  # pylint: disable=broad-exception-caught
            log.warning("Failed to report fatal task failure to backend")
        return

    log.error(
        "Processing failed with exception",
        extra={"error": str(exc), "error_type": type(exc).__name__},
        exc_info=True,
    )
    try:
        client.fail_task(task.task_id, task.task_secret, str(exc))
    except Exception:  # pylint: disable=broad-exception-caught
        log.warning("Failed to report task failure to backend")
