"""SQL expressions for normalized content enrichment state."""

from __future__ import annotations

from sqlalchemy import func, select

from models.sqlalchemy_models import ContentItemEnrichmentState


def effective_document_class_expr():
    """Return the effective document class label expression."""
    return ContentItemEnrichmentState.classification_effective_label


def effective_extraction_schema_expr():
    """Return the effective extraction schema name expression."""
    return ContentItemEnrichmentState.extraction_effective_schema_name


def effective_extraction_data_expr():
    """Return the effective extraction JSON object expression."""
    return ContentItemEnrichmentState.extraction_effective_data_json


def effective_extraction_field_expr(field_name: str):
    """Return one effective extraction field value expression."""
    return effective_extraction_data_expr()[field_name].astext


def review_status_expr(column_name: str):
    """Return one normalized review status expression."""
    return func.nullif(getattr(ContentItemEnrichmentState, column_name), "")


def has_effective_extraction_expr():
    """Return whether a row has effective extraction data."""
    return effective_extraction_data_expr().is_not(None)


def jsonb_object_key_count_expr(value):
    """Count keys in a JSONB object expression."""
    return (
        select(func.count())
        .select_from(func.jsonb_object_keys(value).table_valued("key"))
        .scalar_subquery()
    )


def stored_config_fingerprint_expr(column_name: str):
    """Return one normalized stored config fingerprint expression."""
    return func.nullif(getattr(ContentItemEnrichmentState, column_name), "")


def stored_model_expr(column_name: str):
    """Return one normalized stored model expression."""
    return func.nullif(getattr(ContentItemEnrichmentState, column_name), "")
