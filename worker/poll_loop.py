"""HTTP poll loop replacing Celery task consumption."""

import logging
import shutil
import signal
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import get_settings
from logging_config import LoggingContext, generate_correlation_id, get_logger
from models import (
    WorkerClaimedTask,
    WorkerDownloadedSourceFile,
    WorkerInlineDocumentSource,
    WorkerProcessorContext,
)
from poll_enrichment import (
    handle_enrichment_only_processing as _handle_enrichment_only_processing_run,
)
from poll_enrichment import (
    is_enrichment_only_task as _is_enrichment_only_task_check,
)
from poll_runtime import (
    HttpJobContext,
    TaskProgress,
)
from poll_runtime import (
    coerce_task as _coerce_task,
)
from poll_runtime import (
    compute_backoff_seconds as _compute_backoff_seconds,
)
from poll_runtime import (
    is_fatal_claim_failure as _is_fatal_claim_failure,
)
from poll_runtime import (
    log_result as _log_result,
)
from poll_runtime import (
    report_aborted_result as _report_aborted_result,
)
from poll_runtime import (
    report_completed_result as _report_completed_result,
)
from poll_runtime import (
    report_processing_failure as _report_processing_failure,
)
from poll_runtime import (
    start_task_heartbeat as _start_task_heartbeat,
)
from poll_runtime import (
    stop_task_heartbeat as _stop_task_heartbeat,
)
from poll_runtime import (
    task_log_extra as _task_log_extra,
)
from poll_runtime import (
    upload_extracted_output as _upload_extracted_output,
)
from processor_runtime import ProcessingStage, _run_content_enrichment
from processors import (
    ProcessingResult,
    download_source_file,
    process_audio,
    process_document,
    process_video_metadata,
)
from services.api_client import ApiClient
from services.content_enrichment_training_runner import (
    execute_content_enrichment_training_task,
)

settings = get_settings()
logger = logging.getLogger(__name__)

# Track active task for signal handling
ACTIVE_TASK: WorkerClaimedTask | None = None
CONTENT_ENRICHMENT_TRAINING_TASK_TYPES = frozenset({"train_content_enrichment_model"})

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".html", ".md", ".txt"}
FATAL_FAILURE_THRESHOLD = 3


@dataclass
class WorkerTaskRun:
    """Resolved local state for one claimed worker task."""

    task: WorkerClaimedTask
    processor_context: WorkerProcessorContext
    downloaded_file: WorkerDownloadedSourceFile

    @property
    def relative_path(self) -> str:
        """Return the task-relative source path."""
        return self.task.relative_path

    @property
    def local_path(self) -> Path:
        """Return the local downloaded file path."""
        return self.downloaded_file.local_path

    @property
    def content_item_id(self) -> str | None:
        """Return the resolved backend file id for this run."""
        return self.processor_context.resolved_file_id

    @property
    def output_dir(self) -> Path | None:
        """Return the extracted output directory for this run when available."""
        return self.downloaded_file.resolve_output_dir(settings.WORK_DIR)

    def cleanup(self) -> None:
        """Remove local artifacts created for this task run."""
        if self.output_dir is not None:
            shutil.rmtree(self.output_dir, ignore_errors=True)
        self.local_path.unlink(missing_ok=True)
        with suppress(OSError):
            self.local_path.parent.rmdir()


def _prepare_task_run(task: WorkerClaimedTask) -> WorkerTaskRun:
    """Download the claimed task input and build the local run state."""
    processor_context = task.processor_context()
    inline_document_source = processor_context.metadata.inline_document_source
    if inline_document_source is not None:
        downloaded_file = _materialize_inline_document_source(
            relative_path=task.relative_path,
            local_name_seed=processor_context.resolved_file_id or task.task_id,
            source=inline_document_source,
            content_item_id=processor_context.resolved_file_id,
        )
    else:
        downloaded_file = download_source_file(
            task.relative_path,
            folder_uuid=task.folder_uuid,
            task_secret=task.task_secret,
            content_item_id=processor_context.resolved_file_id,
        )
    return WorkerTaskRun(
        task=task,
        processor_context=processor_context,
        downloaded_file=downloaded_file,
    )


def _materialize_inline_document_source(
    relative_path: str,
    local_name_seed: str,
    source: WorkerInlineDocumentSource,
    *,
    content_item_id: str | None,
) -> WorkerDownloadedSourceFile:
    """Write inline HTML/Markdown task content to a local file for Docling."""
    extension = ".html" if source.format == "html" else ".md"
    work_input = Path(settings.WORK_DIR) / "input" / "inline"
    work_input.mkdir(parents=True, exist_ok=True)
    local_path = work_input / f"{local_name_seed}{extension}"
    local_path.write_text(source.content, encoding="utf-8")
    return WorkerDownloadedSourceFile(
        relative_path=relative_path,
        local_path=local_path,
        content_item_id=content_item_id,
    )


def _is_enrichment_only_task(task: WorkerClaimedTask) -> bool:
    """Return whether the claimed task should rerun enrichment from stored chunks only."""
    return _is_enrichment_only_task_check(task)


def _handle_enrichment_only_processing(
    client: ApiClient,
    task: WorkerClaimedTask,
    log: logging.LoggerAdapter,
) -> None:
    """Rerun classification/extraction from stored chunks without redownloading the file."""
    _handle_enrichment_only_processing_run(
        client,
        task,
        log,
        run_content_enrichment=_run_content_enrichment,
    )


def _handle_processing(
    client: ApiClient,
    task_run: WorkerTaskRun,
    log: logging.LoggerAdapter,
    correlation_id: str,
    progress: TaskProgress | None = None,
) -> ProcessingResult:
    """Run one prepared task through the appropriate processor."""
    task = task_run.task
    task_id = task.task_id
    task_secret = task.task_secret
    relative_path = task_run.relative_path

    if not task_run.local_path.exists():
        log.warning(
            "File not found",
            extra={"absolute_path": str(task_run.local_path)},
        )
        return ProcessingResult(
            status="completed",
            file_path=relative_path,
            message="File missing at processing time",
        )

    job_ctx = HttpJobContext(
        task_id=task_id,
        task_secret=task_secret,
        correlation_id=correlation_id,
        _client=client,
        progress=progress,
    )

    suffix = task_run.local_path.suffix.lower()
    processor_spec = _processor_spec_for_suffix(suffix)
    if processor_spec is None:
        log.info("Unsupported file type", extra={"suffix": suffix})
        return ProcessingResult(
            status="completed",
            file_path=relative_path,
            message="Unsupported file type",
        )

    processor_name, processor = processor_spec
    log.info("Routing to %s", processor_name, extra={"suffix": suffix})
    return processor(
        task_run.local_path,
        relative_path,
        task_run.processor_context,
        job_ctx,
        log,
    )


def _processor_spec_for_suffix(suffix: str):
    """Return the current processor binding for one file suffix."""
    processor_by_suffix = {
        **dict.fromkeys(
            VIDEO_EXTENSIONS, ("video metadata processor", process_video_metadata)
        ),
        **dict.fromkeys(AUDIO_EXTENSIONS, ("audio ASR processor", process_audio)),
        **dict.fromkeys(
            DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS,
            ("document processor", process_document),
        ),
    }
    return processor_by_suffix.get(suffix)


def _handle_training_task(
    client: ApiClient,
    claimed_task: WorkerClaimedTask,
    log: logging.LoggerAdapter,
) -> None:
    execute_content_enrichment_training_task(client, claimed_task, log)


def _handle_downloaded_processing_task(
    client: ApiClient,
    claimed_task: WorkerClaimedTask,
    log: logging.LoggerAdapter,
    correlation_id: str,
    progress: TaskProgress | None = None,
) -> WorkerTaskRun:
    if progress is not None:
        progress.set(ProcessingStage.DOWNLOADING)
    task_run = _prepare_task_run(claimed_task)
    result = _handle_processing(client, task_run, log, correlation_id, progress)
    _log_result(log, result)

    if result.aborted:
        _report_aborted_result(client, claimed_task, result)
        return task_run

    _upload_extracted_output(
        client,
        content_item_id=task_run.content_item_id,
        output_dir=task_run.output_dir,
        task=claimed_task,
        log=log,
    )
    _report_completed_result(client, claimed_task, result)
    return task_run


def _task_handler_for(
    claimed_task: WorkerClaimedTask,
):
    if claimed_task.task_type in CONTENT_ENRICHMENT_TRAINING_TASK_TYPES:
        return _handle_training_task
    if _is_enrichment_only_task(claimed_task):
        return _handle_enrichment_only_processing
    return _handle_downloaded_processing_task


def _process_task(
    client: ApiClient,
    task: WorkerClaimedTask | dict[str, Any],
) -> None:
    """Process a single claimed task."""
    global ACTIVE_TASK  # pylint: disable=global-statement
    claimed_task = _coerce_task(task)
    ACTIVE_TASK = claimed_task
    correlation_id = generate_correlation_id()
    heartbeat: tuple[threading.Event, threading.Thread] | None = None
    task_run: WorkerTaskRun | None = None
    progress = TaskProgress()

    with LoggingContext(correlation_id):
        log = get_logger(__name__, correlation_id)

        log.info(
            "Processing task",
            extra=_task_log_extra(claimed_task),
        )

        heartbeat = _start_task_heartbeat(
            claimed_task.task_id,
            claimed_task.task_secret,
            settings.TASK_HEARTBEAT_INTERVAL_SECONDS,
            progress=progress,
        )

        try:
            handler = _task_handler_for(claimed_task)
            if handler is _handle_downloaded_processing_task:
                task_run = handler(client, claimed_task, log, correlation_id, progress)
            else:
                handler(client, claimed_task, log)
        except Exception as e:  # pylint: disable=broad-exception-caught
            _report_processing_failure(client, claimed_task, e, log)
        finally:
            if task_run is not None:
                task_run.cleanup()
            _stop_task_heartbeat(heartbeat)
            ACTIVE_TASK = None


def run_poll_loop(capabilities: list[str], poll_interval: float = 5.0) -> None:
    """Main poll loop: claim → process → report → repeat."""
    client = ApiClient()
    claim_failures = 0
    fatal_claim_failures = 0

    def signal_handler(sig, _frame):
        # pylint: disable=unused-argument
        logger.info("Received signal %s, shutting down...", sig)
        if ACTIVE_TASK:
            logger.info(
                "Reporting failure for active task %s before exit",
                ACTIVE_TASK.task_id,
            )
            try:
                # We use a fresh client/session to ensure the request goes through during shutdown
                shutdown_client = ApiClient()
                shutdown_client.fail_task(
                    ACTIVE_TASK.task_id,
                    ACTIVE_TASK.task_secret,
                    f"Worker shut down (signal {sig})",
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to report task failure during shutdown: %s", e)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(
        "Starting poll loop (capabilities=%s, interval=%.1fs)",
        capabilities,
        poll_interval,
    )

    while True:
        try:
            task = client.claim_task(capabilities)
        except Exception as e:  # pylint: disable=broad-exception-caught
            claim_failures += 1
            if _is_fatal_claim_failure(e):
                fatal_claim_failures += 1
                logger.error(
                    "Fatal claim error (%d/%d): %s",
                    fatal_claim_failures,
                    FATAL_FAILURE_THRESHOLD,
                    e,
                )
                if fatal_claim_failures >= FATAL_FAILURE_THRESHOLD:
                    logger.critical(
                        "Exiting after repeated fatal claim errors. "
                        "Check worker token/backend auth and worker capabilities."
                    )
                    raise SystemExit(2) from e
            else:
                fatal_claim_failures = 0
                logger.error("Failed to claim task: %s", e)

            sleep_for = _compute_backoff_seconds(poll_interval, claim_failures)
            logger.info("Retrying claim in %.1fs", sleep_for)
            time.sleep(sleep_for)
            continue

        claim_failures = 0
        fatal_claim_failures = 0

        if task is None:
            time.sleep(poll_interval)
            continue

        _process_task(client, task)
