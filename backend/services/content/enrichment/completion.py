"""Worker completion writes for normalized content enrichment."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_settings import EffectiveAiSettings
from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem
from services.ai_settings import (
    document_classification_config_fingerprint,
    document_extraction_config_fingerprint,
    resolve_document_extraction_model_for_schema,
    resolve_document_extraction_provider_for_schema,
)

from .extraction_validation import validate_extraction_payload
from .json_helpers import (
    classification_label,
    ensure_state,
    json_dict,
    json_list,
    numeric,
    payload_document_class,
    string,
)


async def complete_enrichment(
    db: AsyncSession,
    record: IndexedContentItem,
    *,
    settings: EffectiveAiSettings,
    document_classification: dict[str, object] | None,
    document_extraction: dict[str, object] | None,
) -> ContentItemEnrichmentState | None:
    """Apply worker enrichment output to normalized state."""
    _ = db
    if document_classification is None and document_extraction is None:
        return record.enrichment_state
    state = ensure_state(record)
    if document_classification is not None:
        payload = dict(document_classification)
        classification_status = string(payload.get("status")) or "failed"
        state.classification_status = (
            classification_status
            if classification_status in {"completed", "skipped", "failed"}
            else "failed"
        )
        state.classification_error = string(payload.get("error"))
        state.classification_provider = string(payload.get("provider")) or (
            settings.document_classification_provider
        )
        state.classification_system_class_id = (
            string(payload.get("class_id"))
            if state.classification_status == "completed"
            else None
        )
        state.classification_system_label = (
            classification_label(payload)
            if state.classification_status == "completed"
            else None
        )
        state.classification_confidence = (
            numeric(payload.get("confidence"))
            or numeric(payload.get("score"))
            or numeric(payload.get("probability"))
        )
        state.classification_model = string(payload.get("model")) or (
            settings.document_classification_model
        )
        state.classification_config_fingerprint = (
            document_classification_config_fingerprint(settings)
        )
        state.classification_raw_json = payload
        state.classification_evidence_json = json_list(payload.get("evidence"))
        if (
            state.classification_override_label is None
            and state.classification_status == "completed"
        ):
            state.classification_effective_class_id = (
                state.classification_system_class_id
            )
            state.classification_effective_label = state.classification_system_label
        elif state.classification_override_label is None:
            state.classification_effective_class_id = None
            state.classification_effective_label = None
    if document_extraction is not None:
        payload = dict(document_extraction)
        validated = validate_extraction_payload(
            payload,
            settings=settings,
            class_id=state.classification_effective_class_id,
            class_label=state.classification_effective_label
            or payload_document_class(payload),
        )
        state.extraction_status = validated.status
        state.extraction_error = validated.error
        state.extraction_provider = validated.provider or (
            resolve_document_extraction_provider_for_schema()
        )
        state.extraction_system_schema_id = (
            validated.schema_id if validated.trusted else None
        )
        state.extraction_system_schema_name = (
            validated.schema_name if validated.trusted else None
        )
        state.extraction_system_schema_version = (
            validated.schema_version if validated.trusted else None
        )
        state.extraction_system_class_id = (
            validated.class_id if validated.trusted else None
        )
        state.extraction_system_class_label = (
            validated.class_label if validated.trusted else None
        )
        state.extraction_model = (
            validated.model
            or resolve_document_extraction_model_for_schema(
                settings,
                validated.schema_name,
            )
        )
        state.extraction_config_fingerprint = document_extraction_config_fingerprint(
            settings
        )
        state.extraction_raw_json = validated.raw
        state.extraction_data_json = validated.data if validated.trusted else {}
        state.extraction_fields_json = validated.fields if validated.trusted else {}
        state.extraction_summary_json = validated.summary
        if validated.trusted:
            state.extraction_effective_data_json = {
                **validated.data,
                **json_dict(state.extraction_override_data_json),
            }
            state.extraction_effective_schema_id = state.extraction_system_schema_id
            state.extraction_effective_schema_name = state.extraction_system_schema_name
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
        else:
            state.extraction_effective_data_json = {}
            state.extraction_effective_schema_id = None
            state.extraction_effective_schema_name = None
            state.extraction_effective_class_id = None
            state.extraction_effective_class_label = None
    return state
