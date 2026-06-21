"""Content-enrichment task helpers for the worker poll loop."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from models import WorkerClaimedTask
from processors import SimpleChunk
from services.backend_client import BackendClient


def is_enrichment_only_task(task: WorkerClaimedTask) -> bool:
    """Return whether the claimed task should rerun enrichment from stored chunks only."""
    processing_config = task.processing_metadata().get("processing_config")
    return bool(
        isinstance(processing_config, dict)
        and processing_config.get("enrichment_only") is True
    )


def handle_enrichment_only_processing(
    client: BackendClient,
    task: WorkerClaimedTask,
    log: logging.LoggerAdapter,
    *,
    run_content_enrichment: Callable[..., tuple[Any, Any]],
) -> None:
    """Rerun classification/extraction from stored chunks without redownloading the file."""
    source = client.get_content_enrichment_task_source(task.task_id, task.task_secret)
    if not source.chunks:
        raise RuntimeError(
            "No stored chunks available for enrichment-only rerun; "
            "run full processing first"
        )

    metadata = task.processing_metadata()
    if source.current_document_class:
        metadata["current_document_class"] = source.current_document_class

    chunks = [
        SimpleChunk(
            chunk.text,
            page_numbers=chunk.page_numbers,
            doc_refs=chunk.doc_refs,
            images=chunk.images,
            chunk_index=chunk.chunk_index,
            headings=chunk.headings,
            captions=chunk.captions,
        )
        for chunk in source.chunks
        if isinstance(chunk.text, str) and chunk.text.strip()
    ]
    if not chunks:
        raise RuntimeError(
            "Stored chunks for enrichment-only rerun were empty after normalization"
        )

    classification, extraction = run_content_enrichment(
        text="\n\n".join(chunk.text for chunk in chunks),
        chunks=chunks,
        metadata=metadata,
        runtime_config=client.get_config(force_refresh=True),
        log=log,
        task_id=task.task_id,
        task_secret=task.task_secret,
    )
    processing_config = metadata.get("processing_config")
    client.complete_task(
        task.task_id,
        task.task_secret,
        processing_config=processing_config,
        document_classification=classification,
        document_extraction=extraction,
    )
