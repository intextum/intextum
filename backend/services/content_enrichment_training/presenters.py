"""Response mapping helpers for content-enrichment training."""

from __future__ import annotations

from models.content.enrichment_training import (
    ContentEnrichmentFineTuneJobEntry,
    ContentEnrichmentModelRegistryEntry,
    ContentEnrichmentTrainingDatasetSummary,
)
from models.sqlalchemy_models import (
    ContentEnrichmentFineTuneJob,
    ContentEnrichmentModelRegistry,
)


def iso_or_none(value) -> str | None:
    return value.isoformat() if value is not None else None


def job_entry(row: ContentEnrichmentFineTuneJob) -> ContentEnrichmentFineTuneJobEntry:
    return ContentEnrichmentFineTuneJobEntry(
        id=row.id,
        registry_model_id=row.registry_model_id,
        queue_task_id=row.queue_task_id,
        status=row.status,
        target_kind=row.target_kind,
        training_method=row.training_method,
        base_model=row.base_model,
        target_name=row.target_name,
        config_fingerprint=row.config_fingerprint,
        dataset_summary=ContentEnrichmentTrainingDatasetSummary(
            reviewed_example_count=int(
                (row.dataset_summary_json or {}).get("reviewed_example_count", 0)
            )
        ),
        error_message=row.error_message,
        requested_by=row.requested_by,
        requested_by_sub=row.requested_by_sub,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        started_at=iso_or_none(row.started_at),
        completed_at=iso_or_none(row.completed_at),
    )


def model_entry(
    row: ContentEnrichmentModelRegistry,
    *,
    is_active: bool,
) -> ContentEnrichmentModelRegistryEntry:
    return ContentEnrichmentModelRegistryEntry(
        id=row.id,
        target_kind=row.target_kind,
        training_method=row.training_method,
        status=row.status,
        base_model=row.base_model,
        target_name=row.target_name,
        config_fingerprint=row.config_fingerprint,
        reviewed_example_count=row.reviewed_example_count,
        artifact_path=row.artifact_path,
        metrics=dict(row.metrics_json) if isinstance(row.metrics_json, dict) else None,
        created_by=row.created_by,
        is_active=is_active,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )
