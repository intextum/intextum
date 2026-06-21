"""Derived lifecycle and review readiness for content enrichment."""

from __future__ import annotations

from datetime import datetime

from models.content.items import (
    ContentClassificationView,
    ContentEnrichmentLifecycleInfo,
    ContentExtractionView,
)

from .json_helpers import REVIEW_STATUSES


def lifecycle_info(
    *,
    processed_at: datetime | None,
    enabled: bool,
    current_fingerprint: str,
    stored_fingerprint: str | None,
) -> ContentEnrichmentLifecycleInfo | None:
    if processed_at is None and stored_fingerprint is None:
        return None
    if not enabled:
        return ContentEnrichmentLifecycleInfo(
            stale=False,
            current_enabled=False,
            current_config_fingerprint=current_fingerprint,
            stored_config_fingerprint=stored_fingerprint,
        )
    if stored_fingerprint is None:
        return ContentEnrichmentLifecycleInfo(
            stale=True,
            reason="missing_result",
            current_enabled=True,
            current_config_fingerprint=current_fingerprint,
            stored_config_fingerprint=None,
        )
    if stored_fingerprint != current_fingerprint:
        return ContentEnrichmentLifecycleInfo(
            stale=True,
            reason="config_changed",
            current_enabled=True,
            current_config_fingerprint=current_fingerprint,
            stored_config_fingerprint=stored_fingerprint,
        )
    return ContentEnrichmentLifecycleInfo(
        stale=False,
        current_enabled=True,
        current_config_fingerprint=current_fingerprint,
        stored_config_fingerprint=stored_fingerprint,
    )


def content_review_state(
    classification: ContentClassificationView | None,
    extraction: ContentExtractionView | None,
    *,
    classification_lifecycle: ContentEnrichmentLifecycleInfo | None,
    extraction_lifecycle: ContentEnrichmentLifecycleInfo | None,
):
    """Return the derived review state for typed enrichment views."""
    if (
        classification_lifecycle is not None
        and classification_lifecycle.stale
        or extraction_lifecycle is not None
        and extraction_lifecycle.stale
    ):
        return "stale"
    statuses: list[str] = []
    if classification is not None and (
        classification.label or classification.review_status == "dismissed"
    ):
        statuses.append(classification.review_status)
    if extraction is not None:
        statuses.append(extraction.review_status)
    if not statuses:
        return "none"
    if all(status in REVIEW_STATUSES for status in statuses):
        return "reviewed"
    return "needs_review"
