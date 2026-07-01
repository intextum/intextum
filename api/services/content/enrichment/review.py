"""Unified review writes for normalized content enrichment."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import (
    ContentItemEnrichmentState,
    IndexedContentItem,
    utc_now,
)
from models.user import User
from services.content.audit import ContentAuditService

from .json_helpers import (
    ensure_state,
    json_dict,
    json_list,
    normalized_lookup,
    sorted_field_names,
    string,
)

CLASSIFICATION_DISMISS_REASONS = {"not_a_document", "no_fitting_class"}
EXTRACTION_DISMISS_REASONS_INPUT = {"not_extractable", "schema_mismatch"}
EXTRACTION_DISMISS_REASON_CASCADE = "no_class"

Side = Literal["classification", "extraction"]


class ContentReviewSubmitError(ValueError):
    """Raised when a unified review submission cannot be applied."""


class ContentReviewConflictError(ContentReviewSubmitError):
    """Raised when a review submission conflicts with current persisted state."""


def _review_metadata(user: User, timestamp: datetime) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "updated_by": user.display_name,
        "updated_at": timestamp.isoformat(),
    }
    if user.normalized_sub is not None:
        metadata["updated_by_sub"] = user.normalized_sub
    return metadata


def _review_history_entry(
    user: User,
    timestamp: datetime,
    *,
    action: str,
    label: str | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"action": action, **_review_metadata(user, timestamp)}
    if label:
        entry["label"] = label
    if fields:
        entry["fields"] = [field for field in fields if field.strip()]
    return entry


def _keeps_existing_correction(
    review_status: str | None, matches_current: bool
) -> bool:
    return review_status == "corrected" and matches_current


def _diff_extraction_fields(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return changed fields keyed by field name with before/after values."""
    changes: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value != after_value:
            changes[key] = {"before": before_value, "after": after_value}
    return changes


def _finalize_review_side(
    state: ContentItemEnrichmentState,
    *,
    side: Side,
    status: str,
    dismissed_reason: str | None,
    user: User,
    now: datetime,
    history_entry: dict[str, Any],
) -> None:
    """Stamp review-status fields and append a history entry for one side."""
    setattr(state, f"{side}_review_status", status)
    setattr(state, f"{side}_dismissed_reason", dismissed_reason)
    setattr(state, f"{side}_reviewed_by", user.display_name)
    setattr(state, f"{side}_reviewed_by_sub", user.normalized_sub)
    setattr(state, f"{side}_reviewed_at", now)
    history_column = f"{side}_review_history_json"
    history = json_list(getattr(state, history_column))
    history.append(history_entry)
    setattr(state, history_column, history)


async def _audit_review_event(
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    side: Side,
    action: str,
    summary: str,
    metadata: dict[str, Any],
    user: User,
) -> None:
    """Append a uniform review audit event for one side."""
    await ContentAuditService(db).append_for_record(
        record,
        event_type=f"content.review.{side}_{action}",
        event_group="review",
        status="completed",
        summary=summary,
        metadata=metadata,
        user=user,
        source="ui",
    )


async def _dismiss_classification(
    state: ContentItemEnrichmentState,
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    reason: str,
    user: User,
    now: datetime,
) -> None:
    if reason not in CLASSIFICATION_DISMISS_REASONS:
        raise ContentReviewSubmitError(
            "classification_dismiss_reason must be one of "
            + ", ".join(sorted(CLASSIFICATION_DISMISS_REASONS))
        )
    before_label = state.classification_effective_label
    state.classification_override_class_id = None
    state.classification_override_label = None
    state.classification_effective_class_id = None
    state.classification_effective_label = None
    history_entry = _review_history_entry(user, now, action="dismissed") | {
        "reason": reason
    }
    _finalize_review_side(
        state,
        side="classification",
        status="dismissed",
        dismissed_reason=reason,
        user=user,
        now=now,
        history_entry=history_entry,
    )
    await _audit_review_event(
        db,
        record,
        side="classification",
        action="dismissed",
        summary=f"Classification dismissed ({reason})",
        metadata={"reason": reason, "before_label": before_label, "after_label": None},
        user=user,
    )


async def _dismiss_extraction(
    state: ContentItemEnrichmentState,
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    reason: str | None,
    user: User,
    now: datetime,
) -> None:
    resolved_reason = (
        reason if reason is not None else EXTRACTION_DISMISS_REASON_CASCADE
    )
    if (
        resolved_reason not in EXTRACTION_DISMISS_REASONS_INPUT
        and resolved_reason != EXTRACTION_DISMISS_REASON_CASCADE
    ):
        raise ContentReviewSubmitError(
            "extraction_dismiss_reason must be one of "
            + ", ".join(sorted(EXTRACTION_DISMISS_REASONS_INPUT))
        )
    before_fields = sorted_field_names(json_dict(state.extraction_effective_data_json))
    state.extraction_override_data_json = None
    state.extraction_override_class_id = None
    state.extraction_override_class_label = None
    state.extraction_effective_data_json = {}
    state.extraction_effective_class_id = None
    state.extraction_effective_class_label = None
    state.extraction_effective_schema_id = None
    state.extraction_effective_schema_name = None
    history_entry = _review_history_entry(user, now, action="dismissed") | {
        "reason": resolved_reason
    }
    _finalize_review_side(
        state,
        side="extraction",
        status="dismissed",
        dismissed_reason=resolved_reason,
        user=user,
        now=now,
        history_entry=history_entry,
    )
    await _audit_review_event(
        db,
        record,
        side="extraction",
        action="dismissed",
        summary=f"Extraction dismissed ({resolved_reason})",
        metadata={
            "reason": resolved_reason,
            "before_field_count": len(before_fields or []),
            "before_fields": before_fields,
        },
        user=user,
    )


async def _clear_classification(
    state: ContentItemEnrichmentState,
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    user: User,
    now: datetime,
) -> None:
    """Reset classification to an unreviewed, unclassified state."""
    before_label = state.classification_effective_label
    state.classification_override_class_id = None
    state.classification_override_label = None
    state.classification_effective_class_id = None
    state.classification_effective_label = None
    state.classification_review_status = None
    state.classification_dismissed_reason = None
    state.classification_reviewed_by = None
    state.classification_reviewed_by_sub = None
    state.classification_reviewed_at = None
    history = json_list(state.classification_review_history_json)
    history.append(_review_history_entry(user, now, action="cleared"))
    state.classification_review_history_json = history
    await _audit_review_event(
        db,
        record,
        side="classification",
        action="cleared",
        summary="Classification cleared",
        metadata={"before_label": before_label, "after_label": None},
        user=user,
    )


async def _clear_extraction(
    state: ContentItemEnrichmentState,
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    user: User,
    now: datetime,
) -> None:
    """Reset extraction to an unreviewed, empty state."""
    before_fields = sorted_field_names(json_dict(state.extraction_effective_data_json))
    state.extraction_override_data_json = None
    state.extraction_override_class_id = None
    state.extraction_override_class_label = None
    state.extraction_effective_data_json = {}
    state.extraction_effective_class_id = None
    state.extraction_effective_class_label = None
    state.extraction_effective_schema_id = None
    state.extraction_effective_schema_name = None
    state.extraction_review_status = None
    state.extraction_dismissed_reason = None
    state.extraction_reviewed_by = None
    state.extraction_reviewed_by_sub = None
    state.extraction_reviewed_at = None
    history = json_list(state.extraction_review_history_json)
    history.append(_review_history_entry(user, now, action="cleared"))
    state.extraction_review_history_json = history
    await _audit_review_event(
        db,
        record,
        side="extraction",
        action="cleared",
        summary="Extraction cleared",
        metadata={
            "before_field_count": len(before_fields or []),
            "before_fields": before_fields,
        },
        user=user,
    )


async def _accept_or_correct_classification(
    state: ContentItemEnrichmentState,
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    classification_label: str | None,
    user: User,
    now: datetime,
) -> None:
    submitted_label = string(classification_label)
    if submitted_label is None:
        raise ContentReviewSubmitError(
            "classification_label must be a non-empty string"
        )
    before_label = state.classification_effective_label
    current_label = state.classification_effective_label
    system_label = state.classification_system_label
    matches_current = submitted_label == current_label
    matches_system = system_label is not None and submitted_label == system_label
    if not _keeps_existing_correction(
        state.classification_review_status, matches_current
    ):
        if matches_system:
            state.classification_override_class_id = None
            state.classification_override_label = None
            state.classification_effective_class_id = (
                state.classification_system_class_id
            )
            state.classification_effective_label = state.classification_system_label
            new_status = "accepted"
        else:
            state.classification_override_label = submitted_label
            state.classification_effective_label = submitted_label
            new_status = "corrected"
    else:
        new_status = state.classification_review_status or "corrected"
    history_entry = _review_history_entry(
        user, now, action=new_status, label=submitted_label
    )
    _finalize_review_side(
        state,
        side="classification",
        status=new_status,
        dismissed_reason=None,
        user=user,
        now=now,
        history_entry=history_entry,
    )
    await _audit_review_event(
        db,
        record,
        side="classification",
        action=new_status,
        summary=f"Classification {new_status}",
        metadata={
            "classification_label": submitted_label,
            "before_label": before_label,
            "after_label": state.classification_effective_label,
        },
        user=user,
    )


async def _accept_or_correct_extraction(
    state: ContentItemEnrichmentState,
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    extraction_data: dict[str, Any] | None,
    user: User,
    now: datetime,
) -> None:
    if extraction_data is None or not isinstance(extraction_data, dict):
        raise ContentReviewSubmitError("extraction_data must be a JSON object")
    system_data = json_dict(state.extraction_data_json)
    document_class = state.classification_effective_label
    system_extraction_class = state.extraction_system_class_label
    if (
        document_class
        and system_extraction_class
        and normalized_lookup(document_class)
        != normalized_lookup(system_extraction_class)
        and extraction_data == system_data
    ):
        raise ContentReviewConflictError(
            "Extraction result belongs to a different document class"
        )
    current_data = json_dict(state.extraction_effective_data_json)
    matches_current = extraction_data == current_data
    matches_system = extraction_data == system_data
    field_changes = _diff_extraction_fields(current_data, extraction_data)
    if not _keeps_existing_correction(state.extraction_review_status, matches_current):
        if matches_system:
            state.extraction_override_data_json = None
            state.extraction_override_class_id = None
            state.extraction_override_class_label = None
            state.extraction_effective_data_json = system_data
            new_status = "accepted"
        else:
            state.extraction_override_data_json = extraction_data
            state.extraction_override_class_id = state.classification_effective_class_id
            state.extraction_override_class_label = state.classification_effective_label
            state.extraction_effective_data_json = extraction_data
            new_status = "corrected"
    else:
        new_status = state.extraction_review_status or "corrected"
    state.extraction_effective_class_id = (
        state.extraction_override_class_id
        or state.extraction_system_class_id
        or state.classification_effective_class_id
    )
    state.extraction_effective_class_label = (
        state.extraction_override_class_label
        or state.extraction_system_class_label
        or state.classification_effective_label
    )
    fields = sorted_field_names(extraction_data)
    history_entry = _review_history_entry(user, now, action=new_status, fields=fields)
    _finalize_review_side(
        state,
        side="extraction",
        status=new_status,
        dismissed_reason=None,
        user=user,
        now=now,
        history_entry=history_entry,
    )
    await _audit_review_event(
        db,
        record,
        side="extraction",
        action=new_status,
        summary=f"Extraction {new_status}",
        metadata={
            "fields": fields,
            "field_changes": field_changes,
            "changed_field_count": len(field_changes),
        },
        user=user,
    )


async def submit_content_enrichment_review(
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    user: User,
    classification_label: str | None = None,
    classification_dismiss_reason: str | None = None,
    extraction_data: dict[str, Any] | None = None,
    extraction_dismiss_reason: str | None = None,
    update_classification: bool = False,
    update_extraction: bool = False,
    dismiss_classification: bool = False,
    dismiss_extraction: bool = False,
    reset_classification: bool = False,
    reset_extraction: bool = False,
) -> IndexedContentItem:
    """Persist one unified review decision for a file's enrichment data."""
    now = utc_now()
    state = ensure_state(record)
    handled_reviewable_part = False

    if reset_classification:
        await _clear_classification(state, db, record, user=user, now=now)
        handled_reviewable_part = True
        # Cascade: no class means any prior extraction no longer applies.
        if not reset_extraction and not dismiss_extraction and not update_extraction:
            reset_extraction = True

    if reset_extraction:
        await _clear_extraction(state, db, record, user=user, now=now)
        handled_reviewable_part = True

    if dismiss_classification:
        if classification_dismiss_reason is None:
            raise ContentReviewSubmitError(
                "classification_dismiss_reason is required when dismissing classification"
            )
        await _dismiss_classification(
            state,
            db,
            record,
            reason=classification_dismiss_reason,
            user=user,
            now=now,
        )
        handled_reviewable_part = True
        # Cascade: no class means no schema applies.
        if not dismiss_extraction and not update_extraction:
            dismiss_extraction = True
            extraction_dismiss_reason = EXTRACTION_DISMISS_REASON_CASCADE

    if dismiss_extraction:
        await _dismiss_extraction(
            state,
            db,
            record,
            reason=extraction_dismiss_reason,
            user=user,
            now=now,
        )
        handled_reviewable_part = True

    if update_classification:
        await _accept_or_correct_classification(
            state,
            db,
            record,
            classification_label=classification_label,
            user=user,
            now=now,
        )
        handled_reviewable_part = True

    if update_extraction:
        await _accept_or_correct_extraction(
            state,
            db,
            record,
            extraction_data=extraction_data,
            user=user,
            now=now,
        )
        handled_reviewable_part = True

    if not handled_reviewable_part:
        raise ContentReviewSubmitError(
            "No reviewable classification or extraction data"
        )

    await db.commit()
    await db.refresh(record)
    return record
