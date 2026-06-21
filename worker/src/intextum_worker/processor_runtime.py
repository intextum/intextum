"""Shared runtime helpers for worker file processors."""

from __future__ import annotations

import ctypes
import logging
import signal
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from intextum_worker.config import get_settings
from intextum_worker.models import (
    WorkerDocumentClassificationResult,
    WorkerDocumentExtractionResult,
    WorkerRuntimeConfig,
)
from intextum_worker.services.content_enrichment import (
    classify_document,
    describe_document_extraction_plan,
    extract_document_data,
)
from intextum_worker.services.content_enrichment.registry import (
    LANGGRAPH_EXTRACT_PROVIDER,
)

# Type alias for logger that accepts both Logger and LoggerAdapter
LoggerType = logging.Logger | logging.LoggerAdapter

DEFAULT_CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS = 300.0


class ProcessingStage:
    """Stable stage keys reported to the backend and mapped to UI labels."""

    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    EXTRACTING_IMAGES = "extracting_images"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    INDEXING = "indexing"


class ContentEnrichmentStageTimeout(TimeoutError):
    """Raised when a model-backed enrichment stage exceeds its deadline."""


class JobContext(Protocol):
    """Protocol for job context providing abort checking and stage reporting."""

    def is_superseded(self) -> bool:
        """Check if this job has been superseded by a newer one."""

    def set_stage(self, stage: str) -> None:
        """Record the active processing stage for heartbeat reporting."""

    @property
    def correlation_id(self) -> str:
        """Get the correlation ID for this job."""


@dataclass
# pylint: disable=too-many-instance-attributes
class ProcessingResult:
    """Result of a file processing operation."""

    status: str
    file_path: str
    message: str
    chunks_created: int = 0
    images_classified: int = 0
    processing_time_ms: int = 0
    aborted: bool = False
    error: str | None = None
    metadata: dict = field(default_factory=dict)


# pylint: disable=too-few-public-methods
class SimpleChunk:
    """Minimal chunk implementation for synthetic text chunks."""

    def __init__(
        self,
        text: str,
        *,
        page_numbers: list[int] | None = None,
        doc_refs: list[str] | None = None,
        images: list[str] | None = None,
        chunk_index: int | None = None,
        headings: list[str] | None = None,
        captions: list[str] | None = None,
    ):
        self.text = text
        self.meta = None
        self.page_numbers = list(page_numbers or [])
        self.doc_refs = list(doc_refs or [])
        self.images = list(images or [])
        self.chunk_index = chunk_index
        self.headings = list(headings or [])
        self.captions = list(captions or [])


def _aborted_result(relative_path: str, message: str) -> ProcessingResult:
    """Build a standard aborted processing result."""
    return ProcessingResult(
        status="aborted",
        file_path=relative_path,
        message=message,
        aborted=True,
    )


def _abort_if_superseded(
    job_ctx: JobContext,
    log: LoggerType,
    *,
    relative_path: str,
    log_message: str,
    result_message: str,
) -> ProcessingResult | None:
    """Return an aborted result when the current job has been superseded."""
    if not job_ctx.is_superseded():
        return None

    log.info(log_message)
    return _aborted_result(relative_path, result_message)


def _document_text_from_chunks(chunks: list) -> str:
    """Flatten chunk text into one document string for enrichment passes."""
    parts = [
        str(chunk.text).strip()
        for chunk in chunks
        if getattr(chunk, "text", None) and str(chunk.text).strip()
    ]
    return "\n\n".join(parts)


def _processing_flag(
    metadata: dict,
    key: str,
    *,
    default: bool,
) -> bool:
    """Resolve one boolean processing flag from task metadata or runtime defaults."""
    raw_processing_config = metadata.get("processing_config")
    if isinstance(raw_processing_config, dict) and key in raw_processing_config:
        raw_value = raw_processing_config.get(key)
        if isinstance(raw_value, bool):
            return raw_value
    return default


def _optional_processing_flag(metadata: dict, key: str) -> bool | None:
    """Return an explicitly-set boolean processing flag, or ``None`` if absent."""
    raw_processing_config = metadata.get("processing_config")
    if isinstance(raw_processing_config, dict) and key in raw_processing_config:
        raw_value = raw_processing_config.get(key)
        if isinstance(raw_value, bool):
            return raw_value
    return None


def _processing_text(
    metadata: dict,
    key: str,
) -> str | None:
    """Resolve one optional string value from task processing config."""
    raw_processing_config = metadata.get("processing_config")
    if not isinstance(raw_processing_config, dict):
        return None
    raw_value = raw_processing_config.get(key)
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    return None


def _content_enrichment_stage_timeout_seconds(
    runtime_config: WorkerRuntimeConfig | None = None,
) -> float:
    """Return the configured per-stage enrichment timeout in seconds."""
    raw_value = (
        getattr(runtime_config, "content_enrichment_stage_timeout_seconds", None)
        if runtime_config is not None
        else None
    )
    if raw_value is None:
        raw_value = getattr(
            get_settings(),
            "CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS",
            DEFAULT_CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS,
        )
    try:
        timeout_seconds = float(raw_value)
    except (TypeError, ValueError):
        timeout_seconds = DEFAULT_CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS
    return max(0.0, timeout_seconds)


def _duration_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _async_raise_in_thread(thread_ident: int, exc_type: type | None) -> int:
    """Schedule (or clear) an async exception in the target Python thread.

    Pass exc_type=None to clear a previously-set pending exception. Returns the
    number of thread states modified. Delivery happens at the next bytecode
    boundary; C-level blocking calls only interrupt once they yield back to
    Python, which matches the signal-based path's caveat.
    """
    set_async_exc = ctypes.pythonapi.PyThreadState_SetAsyncExc
    exc_arg = ctypes.py_object(exc_type) if exc_type is not None else ctypes.py_object()
    affected = set_async_exc(ctypes.c_ulong(thread_ident), exc_arg)
    if affected > 1:
        set_async_exc(ctypes.c_ulong(thread_ident), ctypes.py_object())
        return 0
    return affected


@contextmanager
def _enrichment_stage_deadline(
    stage: str,
    *,
    timeout_seconds: float,
) -> Iterator[None]:
    """Interrupt a model stage that runs longer than its deadline.

    Uses SIGALRM on the main thread (the worker's normal path) and a
    Timer-driven async-exception fallback elsewhere, so off-main-thread
    execution actually times out instead of silently no-opping.
    """
    if timeout_seconds <= 0:
        yield
        return

    error_message = f"{stage} timed out after {timeout_seconds:g}s"
    on_main_thread = threading.current_thread() is threading.main_thread() and hasattr(
        signal, "setitimer"
    )

    if on_main_thread:
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)

        def _raise_timeout(_signum, _frame):
            raise ContentEnrichmentStageTimeout(error_message)

        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_timer[0] > 0:
                signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        return

    target_thread_ident = threading.get_ident()
    fired = threading.Event()

    def _fire_timeout() -> None:
        fired.set()
        _async_raise_in_thread(target_thread_ident, ContentEnrichmentStageTimeout)

    timer = threading.Timer(timeout_seconds, _fire_timeout)
    timer.daemon = True
    timer.start()
    try:
        yield
    except ContentEnrichmentStageTimeout as exc:
        raise ContentEnrichmentStageTimeout(error_message) from exc
    finally:
        timer.cancel()
        if fired.is_set():
            _async_raise_in_thread(target_thread_ident, None)


def _run_content_enrichment(
    *,
    text: str,
    chunks: list,
    metadata: dict,
    runtime_config: WorkerRuntimeConfig,
    log: LoggerType,
    task_id: str | None = None,
    task_secret: str | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> tuple[WorkerDocumentClassificationResult, WorkerDocumentExtractionResult]:
    """Run optional classification and structured extraction for one document."""

    def _report_stage(stage: str) -> None:
        if on_stage is not None:
            on_stage(stage)

    timeout_seconds = _content_enrichment_stage_timeout_seconds(runtime_config)
    classification_enabled = runtime_config.document_classification_enabled
    extraction_enabled = runtime_config.document_extraction_enabled
    # ``document_enrichment`` is a per-task master override: when present it forces
    # both stages on/off, ignoring the per-stage runtime defaults. When absent each
    # stage is gated independently so extraction can still run on a forced/existing
    # class while classification is disabled (and vice versa).
    enrichment_override = _optional_processing_flag(metadata, "document_enrichment")
    if enrichment_override is not None:
        classification_enabled = enrichment_override
        extraction_enabled = enrichment_override
    enrichment_enabled = classification_enabled or extraction_enabled

    classification = WorkerDocumentClassificationResult(
        status="skipped",
        source="disabled",
        provider=runtime_config.document_classification_provider,
        error="Document classification disabled",
    )
    extraction = WorkerDocumentExtractionResult(
        status="skipped",
        provider=LANGGRAPH_EXTRACT_PROVIDER,
        error="Structured extraction disabled",
    )

    forced_document_class_label = _processing_text(
        metadata,
        "forced_document_class_label",
    )
    forced_document_class_id = _processing_text(
        metadata,
        "forced_document_class_id",
    )
    has_forced_document_class = bool(
        forced_document_class_label or forced_document_class_id
    )

    log.info(
        "Content enrichment started",
        extra={
            "enrichment_enabled": enrichment_enabled,
            "classification_enabled": classification_enabled,
            "extraction_enabled": extraction_enabled,
            "forced_document_class": has_forced_document_class,
            "text_chars": len(text),
            "chunk_count": len(chunks),
            "classification_provider": runtime_config.document_classification_provider,
            "extraction_provider": LANGGRAPH_EXTRACT_PROVIDER,
            "classification_label_count": len(
                runtime_config.document_classification_labels
            ),
            "extraction_schema_count": len(runtime_config.document_extraction_schemas),
            "stage_timeout_seconds": timeout_seconds,
        },
    )

    if not enrichment_enabled:
        log.info("Content enrichment skipped because it is disabled")
        return classification, extraction

    if classification_enabled and not has_forced_document_class:
        _report_stage(ProcessingStage.CLASSIFYING)
        classification_started_at = time.monotonic()
        log.info(
            "Document classification started",
            extra={
                "provider": runtime_config.document_classification_provider,
                "model": runtime_config.document_classification_model,
                "label_count": len(runtime_config.document_classification_labels),
                "text_chars": len(text),
                "chunk_count": len(chunks),
                "timeout_seconds": timeout_seconds,
            },
        )
        try:
            with _enrichment_stage_deadline(
                "Document classification",
                timeout_seconds=timeout_seconds,
            ):
                classification = classify_document(
                    text,
                    model_name=runtime_config.document_classification_model,
                    labels=runtime_config.document_classification_labels,
                    chunks=chunks,
                    provider_name=runtime_config.document_classification_provider,
                    task_id=task_id,
                    task_secret=task_secret,
                )
        except ContentEnrichmentStageTimeout as exc:
            log.warning(
                "Document classification timed out",
                extra={
                    "duration_ms": _duration_ms(classification_started_at),
                    "timeout_seconds": timeout_seconds,
                    "provider": runtime_config.document_classification_provider,
                    "model": runtime_config.document_classification_model,
                },
            )
            classification = WorkerDocumentClassificationResult(
                status="failed",
                source="timeout",
                model=runtime_config.document_classification_model,
                provider=runtime_config.document_classification_provider,
                error=str(exc),
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning(
                "Document classification failed: %s",
                exc,
                extra={
                    "duration_ms": _duration_ms(classification_started_at),
                    "provider": runtime_config.document_classification_provider,
                    "model": runtime_config.document_classification_model,
                },
            )
            classification = WorkerDocumentClassificationResult(
                status="failed",
                source="model",
                model=runtime_config.document_classification_model,
                provider=runtime_config.document_classification_provider,
                error=str(exc),
            )
        else:
            log.info(
                "Document classification finished",
                extra={
                    "duration_ms": _duration_ms(classification_started_at),
                    "status": classification.status,
                    "label": classification.label,
                    "class_id": classification.class_id,
                    "error": classification.error,
                },
            )
    elif has_forced_document_class:
        classification = WorkerDocumentClassificationResult(
            status="skipped",
            source="forced_class",
            provider=runtime_config.document_classification_provider,
            model=runtime_config.document_classification_model,
            class_id=forced_document_class_id,
            label=forced_document_class_label,
            error="Document classification skipped for forced-class enrichment",
        )
        log.info(
            "Document classification skipped for forced-class enrichment",
            extra={
                "forced_document_class_id": forced_document_class_id,
                "forced_document_class_label": forced_document_class_label,
            },
        )

    if not extraction_enabled:
        log.info("Structured extraction skipped because it is disabled")
        return classification, extraction

    _report_stage(ProcessingStage.EXTRACTING)
    existing_document_class = metadata.get("current_document_class")
    if (
        not isinstance(existing_document_class, str)
        or not existing_document_class.strip()
    ):
        existing_document_class = None
    document_class_for_extraction = (
        forced_document_class_label or classification.label or existing_document_class
    )
    document_class_id_for_extraction = (
        forced_document_class_id or classification.class_id
    )
    extraction_plan = describe_document_extraction_plan(
        model_name=runtime_config.document_extraction_model,
        llm_model_name=runtime_config.document_extraction_llm_model,
        schemas=runtime_config.document_extraction_schemas,
        document_class=document_class_for_extraction,
        document_class_id=document_class_id_for_extraction,
        schema_models=runtime_config.document_extraction_schema_models,
    )

    extraction_started_at = time.monotonic()
    log.info(
        "Structured extraction started",
        extra={
            "provider": extraction_plan["provider"],
            "providers": extraction_plan["providers"],
            "default_provider": LANGGRAPH_EXTRACT_PROVIDER,
            "model": extraction_plan["model"],
            "models": extraction_plan["models"],
            "default_model": runtime_config.document_extraction_model,
            "schema_matched": extraction_plan["schema_matched"],
            "schema_name": extraction_plan["schema_name"],
            "schema_id": extraction_plan["schema_id"],
            "field_count": extraction_plan["field_count"],
            "field_groups": extraction_plan["field_groups"],
            "available_schemas": extraction_plan["available_schemas"]
            if not extraction_plan["schema_matched"]
            else None,
            "document_class": document_class_for_extraction,
            "document_class_id": document_class_id_for_extraction,
            "schema_count": len(runtime_config.document_extraction_schemas),
            "max_chars": runtime_config.document_extraction_max_chars,
            "chunk_strategy": runtime_config.document_extraction_chunk_strategy,
            "timeout_seconds": timeout_seconds,
        },
    )
    try:
        with _enrichment_stage_deadline(
            "Structured extraction",
            timeout_seconds=timeout_seconds,
        ):
            extraction = extract_document_data(
                text,
                model_name=runtime_config.document_extraction_model,
                llm_model_name=runtime_config.document_extraction_llm_model,
                schemas=runtime_config.document_extraction_schemas,
                document_class=document_class_for_extraction,
                document_class_id=document_class_id_for_extraction,
                max_chars=runtime_config.document_extraction_max_chars,
                llm_max_output_tokens=runtime_config.document_extraction_llm_max_output_tokens,
                chunk_strategy=runtime_config.document_extraction_chunk_strategy,
                chat_max_retries=runtime_config.document_extraction_chat_max_retries,
                chat_evidence_required=runtime_config.document_extraction_chat_evidence_required,
                chat_full_text_threshold_chars=runtime_config.document_extraction_chat_full_text_threshold_chars,
                schema_models=runtime_config.document_extraction_schema_models,
                chunks=chunks,
                task_id=task_id,
                task_secret=task_secret,
            )
    except ContentEnrichmentStageTimeout as exc:
        log.warning(
            "Structured extraction timed out",
            extra={
                "duration_ms": _duration_ms(extraction_started_at),
                "timeout_seconds": timeout_seconds,
                "provider": LANGGRAPH_EXTRACT_PROVIDER,
                "model": runtime_config.document_extraction_model,
                "document_class": document_class_for_extraction,
            },
        )
        extraction = WorkerDocumentExtractionResult(
            status="failed",
            provider=LANGGRAPH_EXTRACT_PROVIDER,
            model=runtime_config.document_extraction_model,
            document_class=document_class_for_extraction,
            document_class_id=document_class_id_for_extraction,
            error=str(exc),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.warning(
            "Structured extraction failed: %s",
            exc,
            extra={
                "duration_ms": _duration_ms(extraction_started_at),
                "provider": LANGGRAPH_EXTRACT_PROVIDER,
                "model": runtime_config.document_extraction_model,
                "document_class": document_class_for_extraction,
            },
        )
        extraction = WorkerDocumentExtractionResult(
            status="failed",
            provider=LANGGRAPH_EXTRACT_PROVIDER,
            model=runtime_config.document_extraction_model,
            document_class=document_class_for_extraction,
            document_class_id=document_class_id_for_extraction,
            error=str(exc),
        )
    else:
        log.info(
            "Structured extraction finished",
            extra={
                "duration_ms": _duration_ms(extraction_started_at),
                "status": extraction.status,
                "schema_name": extraction.schema_name,
                "schema_id": extraction.schema_id,
                "provider": extraction.provider,
                "model": extraction.model,
                "document_class": extraction.document_class,
                "document_class_id": extraction.document_class_id,
                "error": extraction.error,
            },
        )

    log.info(
        "Content enrichment finished",
        extra={
            "classification_status": classification.status,
            "classification_label": classification.label,
            "extraction_status": extraction.status,
            "extraction_schema_name": extraction.schema_name,
        },
    )

    return classification, extraction


def _fallback_chunk_if_empty(
    chunks: list,
    *,
    fallback_text: str,
    log: LoggerType,
    log_message: str,
) -> list:
    """Return a synthetic fallback chunk when Docling produced no chunks."""
    if chunks:
        return chunks

    log.info(log_message)
    return [SimpleChunk(fallback_text)]


def _build_document_fallback_text(
    file_path: Path,
    image_classifications: dict,
) -> str:
    """Build a synthetic fallback chunk for empty image/document conversions."""
    labels = {
        res["label"] for res in image_classifications.values() if res["score"] > 0.4
    }
    label_str = ", ".join(labels) if labels else "No classification"
    return (
        f"File: {file_path.name}\nType: Image/Document\nDetected Content: {label_str}"
    )
