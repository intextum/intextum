"""Enrichment-staleness expressions for flat content stats queries."""

from __future__ import annotations

from sqlalchemy import and_, case, false, or_


from ..enrichment import query_expressions
from .extraction_facets import ExtractionFacetHelpers


class EnrichmentStalenessExpressions:
    """Shared SQL expressions for config/model staleness detection."""

    @staticmethod
    def stored_config_fingerprint_expr(column_name: str):
        return query_expressions.stored_config_fingerprint_expr(column_name)

    @staticmethod
    def stored_model_expr(column_name: str):
        return query_expressions.stored_model_expr(column_name)

    @classmethod
    def stale_enrichment_expr(
        cls,
        *,
        classification_enabled: bool,
        extraction_enabled: bool,
        classification_fingerprint: str,
        extraction_fingerprint: str,
        extraction_model: str,
        extraction_schema_models: dict[str, str] | None,
    ):
        conditions = []

        if classification_enabled:
            stored_classification_fingerprint = cls.stored_config_fingerprint_expr(
                "classification_config_fingerprint"
            )
            conditions.append(
                and_(
                    stored_classification_fingerprint.is_not(None),
                    stored_classification_fingerprint != classification_fingerprint,
                )
            )

        if extraction_enabled:
            stored_extraction_fingerprint = cls.stored_config_fingerprint_expr(
                "extraction_config_fingerprint"
            )
            normalized_schema_models = {
                key: value
                for key, value in (extraction_schema_models or {}).items()
                if isinstance(key, str)
                and key.strip()
                and isinstance(value, str)
                and value.strip()
            }
            current_extraction_model_expr = (
                case(
                    normalized_schema_models,
                    value=ExtractionFacetHelpers.effective_extraction_schema_expr(),
                    else_=extraction_model,
                )
                if normalized_schema_models
                else extraction_model
            )
            stored_extraction_model = cls.stored_model_expr("extraction_model")
            conditions.append(
                or_(
                    and_(
                        stored_extraction_fingerprint.is_not(None),
                        stored_extraction_fingerprint != extraction_fingerprint,
                    ),
                    and_(
                        stored_extraction_model.is_not(None),
                        stored_extraction_model != current_extraction_model_expr,
                    ),
                )
            )

        if not conditions:
            return false()

        return or_(*conditions)
