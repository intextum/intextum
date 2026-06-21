"""Typed models for content enrichment adapter training and registry APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ContentEnrichmentFineTuneTargetKind = Literal["classification"]
ContentEnrichmentFineTuneTrainingMethod = Literal["lora"]
ContentEnrichmentFineTuneJobStatus = Literal["queued", "running", "completed", "failed"]
ContentEnrichmentModelRegistryStatus = Literal[
    "training", "ready", "failed", "archived"
]
ContentEnrichmentReviewedStatus = Literal["accepted", "corrected"]


class ContentEnrichmentTrainingDatasetSummary(BaseModel):
    """Lightweight summary of the reviewed examples included in one training scope."""

    reviewed_example_count: int = Field(ge=0)


class ContentEnrichmentModelRegistryEntry(BaseModel):
    """One trainable/selectable content enrichment model artifact entry."""

    id: str
    target_kind: ContentEnrichmentFineTuneTargetKind
    training_method: ContentEnrichmentFineTuneTrainingMethod
    status: ContentEnrichmentModelRegistryStatus
    base_model: str
    target_name: str | None = None
    config_fingerprint: str
    reviewed_example_count: int = Field(ge=0)
    artifact_path: str | None = None
    metrics: dict[str, Any] | None = None
    created_by: str | None = None
    is_active: bool = False
    created_at: str
    updated_at: str


class ContentEnrichmentFineTuneJobEntry(BaseModel):
    """One backend-managed adapter training job."""

    id: str
    registry_model_id: str
    queue_task_id: str | None = None
    status: ContentEnrichmentFineTuneJobStatus
    target_kind: ContentEnrichmentFineTuneTargetKind
    training_method: ContentEnrichmentFineTuneTrainingMethod
    base_model: str
    target_name: str | None = None
    config_fingerprint: str
    dataset_summary: ContentEnrichmentTrainingDatasetSummary
    error_message: str | None = None
    requested_by: str | None = None
    requested_by_sub: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None


class ContentEnrichmentTrainingCurrentExamples(BaseModel):
    """Reviewed examples currently available for the next training run."""

    classification: int = Field(default=0, ge=0)


class ContentEnrichmentTrainingOverviewResponse(BaseModel):
    """Admin response containing queued training jobs and registered artifacts."""

    jobs: list[ContentEnrichmentFineTuneJobEntry]
    models: list[ContentEnrichmentModelRegistryEntry]
    current_examples: ContentEnrichmentTrainingCurrentExamples = Field(
        default_factory=ContentEnrichmentTrainingCurrentExamples
    )


class ContentEnrichmentTrainingExample(BaseModel):
    """One reviewed example exported in GLiNER2-ready training format."""

    content_item_id: str
    relative_path: str
    input: str
    output: dict[str, Any]
    review_status: ContentEnrichmentReviewedStatus
    reviewed_at: str | None = None
    reviewed_by: str | None = None


class ContentEnrichmentWorkerTrainingDataset(BaseModel):
    """Worker-authenticated reviewed training dataset export for one job task."""

    task_id: str
    training_job_id: str
    registry_model_id: str
    target_kind: ContentEnrichmentFineTuneTargetKind
    training_method: ContentEnrichmentFineTuneTrainingMethod
    base_model: str
    target_name: str | None = None
    config_fingerprint: str
    config_snapshot: dict[str, Any] | None = None
    examples: list[ContentEnrichmentTrainingExample] = Field(default_factory=list)


class CreateContentEnrichmentFineTuneJobRequest(BaseModel):
    """Admin request to queue a new content enrichment adapter training job."""

    target_kind: Literal["classification"]
    training_method: ContentEnrichmentFineTuneTrainingMethod = "lora"
    target_name: str | None = Field(default=None, max_length=255)
    base_model: str | None = Field(default=None, min_length=1, max_length=255)


class ContentEnrichmentModelPromotionResponse(BaseModel):
    """Response payload for promoting a registry model into active settings."""

    model_id: str
    target_kind: ContentEnrichmentFineTuneTargetKind
    target_name: str | None = None
    setting_key: Literal["document_classification_model"]
    setting_value: str
    stale_file_count: int = Field(ge=0)
    newly_stale_file_count: int = Field(ge=0)


class ContentEnrichmentWorkerRegistryModel(BaseModel):
    """Worker-facing metadata for one ready registry-backed adapter."""

    id: str
    target_kind: ContentEnrichmentFineTuneTargetKind
    training_method: ContentEnrichmentFineTuneTrainingMethod
    base_model: str
    target_name: str | None = None
    config_fingerprint: str
    artifact_path: str
