"""Typed API views for normalized content enrichment state."""

from __future__ import annotations

from typing import Any

from models.ai_settings import EffectiveAiSettings
from models.content.items import (
    ContentClassificationResult,
    ContentClassificationView,
    ContentEnrichmentLifecycleInfo,
    ContentEnrichmentReviewInfo,
    ContentEnrichmentView,
    ContentExtractionResult,
    ContentExtractionView,
)
from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem
from services.ai_settings import (
    document_classification_config_fingerprint,
    document_extraction_config_fingerprint,
    resolve_document_extraction_model_for_schema,
    resolve_document_extraction_provider_for_schema,
)

from .json_helpers import (
    REVIEW_STATUSES,
    infer_dtype,
    json_dict,
    json_list,
    json_object,
    review_reason,
    value_is_empty,
)
from .lifecycle import content_review_state, lifecycle_info


def _review_info(
    *,
    status: str | None,
    dismissed_reason: str | None,
    reviewed_by: str | None,
    reviewed_by_sub: str | None,
    reviewed_at,
    history: list[Any] | None,
) -> ContentEnrichmentReviewInfo:
    normalized_status = status if status in REVIEW_STATUSES else "unreviewed"
    return ContentEnrichmentReviewInfo(
        status=normalized_status,
        reviewed=normalized_status in REVIEW_STATUSES,
        dismissed_reason=dismissed_reason if normalized_status == "dismissed" else None,
        reviewed_by=reviewed_by,
        reviewed_by_sub=reviewed_by_sub,
        reviewed_at=reviewed_at,
        history=[entry for entry in history or [] if isinstance(entry, dict)],
    )


def _classification_system_result(
    state: ContentItemEnrichmentState,
) -> ContentClassificationResult | None:
    if not state.classification_system_label:
        return None
    return ContentClassificationResult(
        status=state.classification_status,
        label=state.classification_system_label,
        class_id=state.classification_system_class_id,
        confidence=state.classification_confidence,
        provider=state.classification_provider,
        model=state.classification_model,
        config_fingerprint=state.classification_config_fingerprint,
        evidence=[
            entry
            for entry in json_list(state.classification_evidence_json)
            if isinstance(entry, dict)
        ],
        raw=json_object(state.classification_raw_json),
        error=state.classification_error,
    )


def classification_view(
    state: ContentItemEnrichmentState | None,
) -> ContentClassificationView | None:
    if state is None:
        return None
    is_dismissed = state.classification_review_status == "dismissed"
    if not state.classification_effective_label and not is_dismissed:
        return None
    system = _classification_system_result(state)
    source = "user_override" if state.classification_override_label else "system"
    review = _review_info(
        status=state.classification_review_status,
        dismissed_reason=state.classification_dismissed_reason,
        reviewed_by=state.classification_reviewed_by,
        reviewed_by_sub=state.classification_reviewed_by_sub,
        reviewed_at=state.classification_reviewed_at,
        history=json_list(state.classification_review_history_json),
    )
    evidence = system.evidence if system is not None else []
    needs_review = (
        review.status == "unreviewed"
        and bool(state.classification_effective_label)
        and not evidence
    )
    return ContentClassificationView(
        status=state.classification_status,
        label=state.classification_effective_label,
        class_id=state.classification_effective_class_id,
        confidence=state.classification_confidence,
        provider=state.classification_provider,
        model=state.classification_model,
        config_fingerprint=state.classification_config_fingerprint,
        evidence=evidence,
        raw=json_object(state.classification_raw_json),
        error=state.classification_error,
        source=source,
        system=system,
        review=review,
        review_status=review.status,
        reviewed=review.reviewed,
        dismissed_reason=review.dismissed_reason,  # type: ignore[arg-type]
        needs_review=needs_review,
        review_reasons=[review_reason("missing_evidence")] if needs_review else [],
    )


def _effective_extraction_fields(
    system_fields: dict[str, Any],
    override_data: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    fields = {
        key: dict(value)
        for key, value in system_fields.items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    for field_name, override_value in override_data.items():
        if not isinstance(field_name, str) or not field_name:
            continue
        entry = dict(fields.get(field_name, {}))
        entry["value"] = override_value
        entry["dtype"] = entry.get("dtype") or infer_dtype(override_value)
        entry["required"] = bool(entry.get("required", False))
        entry["evidence"] = []
        entry["item_evidence"] = []
        entry["candidate_values"] = [override_value]
        entry["conflict"] = False
        entry["source"] = "user_override"
        entry["overridden"] = True
        fields[field_name] = entry
    return fields


def _effective_extraction_summary(
    system_summary: dict[str, Any],
    effective_fields: dict[str, dict[str, Any]],
    override_data: dict[str, Any],
    review_status: str,
) -> dict[str, Any]:
    overridden_fields = {
        field_name
        for field_name, field_value in override_data.items()
        if isinstance(field_name, str) and not value_is_empty(field_value)
    }
    missing_required_fields = [
        field_name
        for field_name in system_summary.get("missing_required_fields", [])
        if isinstance(field_name, str) and field_name not in overridden_fields
    ]
    conflicted_fields = [
        field_name
        for field_name in system_summary.get("conflicted_fields", [])
        if isinstance(field_name, str) and field_name not in overridden_fields
    ]
    for field_name, field_payload in effective_fields.items():
        if (
            bool(field_payload.get("required"))
            and value_is_empty(field_payload.get("value"))
            and field_name not in missing_required_fields
        ):
            missing_required_fields.append(field_name)
        if bool(field_payload.get("conflict")) and field_name not in conflicted_fields:
            conflicted_fields.append(field_name)

    fields_without_evidence = [
        field_name
        for field_name, field_payload in effective_fields.items()
        if not value_is_empty(field_payload.get("value"))
        and field_payload.get("source") != "user_override"
        and not (
            isinstance(field_payload.get("evidence"), list)
            and len(field_payload.get("evidence") or []) > 0
        )
    ]
    review_reasons: list[dict[str, Any]] = []
    if review_status == "unreviewed":
        if missing_required_fields:
            review_reasons.append(
                review_reason(
                    "missing_required_fields",
                    fields=missing_required_fields,
                )
            )
        if conflicted_fields:
            review_reasons.append(
                review_reason("conflicted_fields", fields=conflicted_fields)
            )
        if fields_without_evidence:
            review_reasons.append(
                review_reason("missing_evidence", fields=fields_without_evidence)
            )
    summary = dict(system_summary)
    summary.update(
        {
            "missing_required_fields": missing_required_fields,
            "conflicted_fields": conflicted_fields,
            "fields_without_evidence": fields_without_evidence,
            "fields_with_evidence": sum(
                1
                for field_payload in effective_fields.values()
                if isinstance(field_payload.get("evidence"), list)
                and field_payload["evidence"]
            ),
            "needs_review": bool(review_reasons),
            "review_reasons": review_reasons,
        }
    )
    if review_status != "unreviewed":
        summary["review_status"] = review_status
        summary["needs_review"] = False
    return summary


def _extraction_system_result(
    state: ContentItemEnrichmentState,
) -> ContentExtractionResult | None:
    if not state.extraction_system_schema_name and not state.extraction_data_json:
        return None
    return ContentExtractionResult(
        status=state.extraction_status,
        schema_id=state.extraction_system_schema_id,
        schema_name=state.extraction_system_schema_name,
        schema_version=state.extraction_system_schema_version,
        document_class_id=state.extraction_system_class_id,
        document_class=state.extraction_system_class_label,
        provider=state.extraction_provider,
        model=state.extraction_model,
        config_fingerprint=state.extraction_config_fingerprint,
        data=json_dict(state.extraction_data_json),
        fields=json_dict(state.extraction_fields_json),
        summary=json_dict(state.extraction_summary_json),
        raw=json_object(state.extraction_raw_json),
        error=state.extraction_error,
    )


def extraction_view(
    state: ContentItemEnrichmentState | None,
) -> ContentExtractionView | None:
    if state is None:
        return None
    system = _extraction_system_result(state)
    override_data = json_dict(state.extraction_override_data_json)
    effective_data = json_dict(state.extraction_effective_data_json)
    is_dismissed = state.extraction_review_status == "dismissed"
    if system is None and not effective_data and not override_data and not is_dismissed:
        return None
    review = _review_info(
        status=state.extraction_review_status,
        dismissed_reason=state.extraction_dismissed_reason,
        reviewed_by=state.extraction_reviewed_by,
        reviewed_by_sub=state.extraction_reviewed_by_sub,
        reviewed_at=state.extraction_reviewed_at,
        history=json_list(state.extraction_review_history_json),
    )
    fields = _effective_extraction_fields(
        json_dict(state.extraction_fields_json),
        override_data,
    )
    summary = _effective_extraction_summary(
        json_dict(state.extraction_summary_json),
        fields,
        override_data,
        review.status,
    )
    return ContentExtractionView(
        status=state.extraction_status,
        schema_id=state.extraction_effective_schema_id,
        schema_name=state.extraction_effective_schema_name,
        schema_version=state.extraction_system_schema_version,
        document_class_id=state.extraction_effective_class_id,
        document_class=state.extraction_effective_class_label,
        provider=state.extraction_provider,
        model=state.extraction_model,
        config_fingerprint=state.extraction_config_fingerprint,
        data=effective_data,
        fields=fields,
        summary=summary,
        raw=json_object(state.extraction_raw_json),
        error=state.extraction_error,
        source="user_override" if override_data else "system",
        system=system,
        review=review,
        review_status=review.status,
        reviewed=review.reviewed,
        dismissed_reason=review.dismissed_reason,  # type: ignore[arg-type]
        needs_review=bool(summary.get("needs_review")),
    )


def build_content_enrichment_api_views(
    record: IndexedContentItem,
    settings: EffectiveAiSettings | None = None,
) -> tuple[
    ContentClassificationView | None,
    ContentExtractionView | None,
    ContentEnrichmentView,
]:
    """Build typed API views from normalized state."""
    state = record.enrichment_state
    classification = classification_view(state)
    extraction = extraction_view(state)
    classification_lifecycle = None
    extraction_lifecycle = None
    if settings is not None:
        classification_lifecycle = lifecycle_info(
            processed_at=record.processed_at,
            enabled=settings.document_classification_enabled,
            current_fingerprint=document_classification_config_fingerprint(settings),
            stored_fingerprint=state.classification_config_fingerprint
            if state is not None
            else None,
        )
        extraction_lifecycle = lifecycle_info(
            processed_at=record.processed_at,
            enabled=settings.document_extraction_enabled,
            current_fingerprint=document_extraction_config_fingerprint(settings),
            stored_fingerprint=state.extraction_config_fingerprint
            if state is not None
            else None,
        )
        if (
            state is not None
            and extraction_lifecycle is not None
            and not extraction_lifecycle.stale
            and state.extraction_system_schema_name
        ):
            current_model_name = resolve_document_extraction_model_for_schema(
                settings,
                state.extraction_system_schema_name,
            )
            current_provider_name = resolve_document_extraction_provider_for_schema()
            if (
                state.extraction_model != current_model_name
                or state.extraction_provider != current_provider_name
            ):
                extraction_lifecycle = ContentEnrichmentLifecycleInfo(
                    stale=True,
                    reason="config_changed",
                    current_enabled=True,
                    current_config_fingerprint=extraction_lifecycle.current_config_fingerprint,
                    stored_config_fingerprint=state.extraction_config_fingerprint,
                )

    review_state = content_review_state(
        classification,
        extraction,
        classification_lifecycle=classification_lifecycle,
        extraction_lifecycle=extraction_lifecycle,
    )
    return (
        classification,
        extraction,
        ContentEnrichmentView(
            review_state=review_state,
            classification_lifecycle=classification_lifecycle,
            extraction_lifecycle=extraction_lifecycle,
            classification_review_status=classification.review_status
            if classification is not None
            else None,
            extraction_review_status=extraction.review_status
            if extraction is not None
            else None,
        ),
    )
