"""Typed task-queue payloads shared by enqueueing and worker task APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class InlineDocumentSource(BaseModel):
    """Inline document content materialized by the worker before Docling runs."""

    model_config = ConfigDict(extra="ignore")

    format: Literal["html", "md"]
    content: str


class ProcessTaskMetadata(BaseModel):
    """Normalized metadata stored with process tasks."""

    model_config = ConfigDict(extra="ignore")

    content_item_id: str
    size_bytes: int = 0
    modified_time: float = 0.0
    created_time: float = 0.0
    is_symlink: bool = False
    file_extension: str | None = None
    source_name: str | None = None
    allowed_viewers: list[str] | None = None
    denied_viewers: list[str] | None = None
    processing_config: dict[str, Any] | None = None
    inline_document_source: InlineDocumentSource | None = None


class ContentEnrichmentTrainingTaskMetadata(BaseModel):
    """Normalized metadata stored with content enrichment training tasks."""

    model_config = ConfigDict(extra="ignore")

    training_job_id: str
    registry_model_id: str
    target_kind: Literal["classification"]
    training_method: Literal["lora"] = "lora"
    base_model: str
    target_name: str | None = None
    config_fingerprint: str
    reviewed_example_count: int = 0
    config_snapshot: dict[str, Any] | None = None


class EnqueueProcessTask(BaseModel):
    """Input payload for creating a queued process task."""

    content_item_id: str
    folder_uuid: str
    relative_path: str
    metadata: ProcessTaskMetadata
    requested_by_sub: str | None = None


class ClaimedTask(BaseModel):
    """Worker-facing claimed task payload."""

    task_id: str
    task_type: Literal[
        "process",
        "train_content_enrichment_model",
    ]
    content_kind: Literal["document", "image", "video", "training"] | None = None
    content_item_id: str | None = None
    folder_uuid: str
    relative_path: str
    metadata: dict[str, Any]
    task_secret: str | None = None
    retry_count: int


class TaskFailureResult(BaseModel):
    """Result payload for reporting task failure."""

    requeued: bool
    retry_count: int
    new_task_secret: str | None = None
