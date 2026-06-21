"""Class verification flow for normalized content enrichment."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_settings import EffectiveAiSettings
from models.sqlalchemy_models import IndexedContentItem, utc_now
from models.user import User
from services.content.audit import ContentAuditService

from .json_helpers import ensure_state, json_list, normalized_lookup
from .review import _review_history_entry


class ContentVerifyClassError(ValueError):
    """Raised when a requested document class cannot be used for verification."""


def _class_label_from_settings(
    settings: EffectiveAiSettings,
    label: str,
) -> tuple[str, str]:
    normalized = normalized_lookup(label)
    for item in settings.document_classification_labels:
        candidates = [item.name, *item.aliases]
        if any(normalized_lookup(candidate) == normalized for candidate in candidates):
            return item.id, item.name
    raise ContentVerifyClassError("Unknown document class")


def _schema_for_class(settings: EffectiveAiSettings, class_id: str, label: str):
    normalized_id = normalized_lookup(class_id)
    normalized_label = normalized_lookup(label)
    for schema in settings.document_extraction_schemas:
        if normalized_lookup(schema.document_class_id) == normalized_id:
            return schema
        if (
            not schema.document_class_id
            and normalized_lookup(schema.document_class) == normalized_label
        ):
            return schema
    return None


async def verify_content_classification(
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    user: User,
    settings: EffectiveAiSettings,
    classification_label: str,
) -> tuple[IndexedContentItem, str, str, bool]:
    """Store an unconfirmed class correction and clear extraction for other classes."""
    class_id, canonical_label = _class_label_from_settings(
        settings, classification_label
    )
    schema = _schema_for_class(settings, class_id, canonical_label)
    state = ensure_state(record)
    now = utc_now()
    state.classification_override_class_id = class_id
    state.classification_override_label = canonical_label
    state.classification_effective_class_id = class_id
    state.classification_effective_label = canonical_label
    state.classification_review_status = None
    state.classification_dismissed_reason = None
    state.classification_reviewed_by = None
    state.classification_reviewed_by_sub = None
    state.classification_reviewed_at = None

    history = json_list(state.classification_review_history_json)
    history.append(
        _review_history_entry(
            user,
            now,
            action="class_changed",
            label=canonical_label,
        )
    )
    state.classification_review_history_json = history

    extraction_class = state.extraction_effective_class_label
    if extraction_class is None or normalized_lookup(extraction_class) != (
        normalized_lookup(canonical_label)
    ):
        state.extraction_system_schema_id = None
        state.extraction_system_schema_name = None
        state.extraction_system_schema_version = None
        state.extraction_system_class_id = None
        state.extraction_system_class_label = None
        state.extraction_provider = None
        state.extraction_model = None
        state.extraction_status = None
        state.extraction_error = None
        state.extraction_config_fingerprint = None
        state.extraction_raw_json = None
        state.extraction_data_json = {}
        state.extraction_fields_json = {}
        state.extraction_summary_json = {}
        state.extraction_override_data_json = None
        state.extraction_override_class_id = None
        state.extraction_override_class_label = None
        state.extraction_effective_data_json = {}
        state.extraction_effective_schema_id = None
        state.extraction_effective_schema_name = None
        state.extraction_effective_class_id = None
        state.extraction_effective_class_label = None
        state.extraction_review_status = None
        state.extraction_dismissed_reason = None
        state.extraction_reviewed_by = None
        state.extraction_reviewed_by_sub = None
        state.extraction_reviewed_at = None

    await ContentAuditService(db).append_for_record(
        record,
        event_type="content.verify.class_changed",
        event_group="review",
        status="completed",
        summary=f"Document class changed to {canonical_label}",
        metadata={
            "classification_label": canonical_label,
            "classification_id": class_id,
            "queued_extraction": schema is not None,
        },
        user=user,
        source="ui",
    )
    await db.commit()
    await db.refresh(record)
    return record, class_id, canonical_label, schema is not None
