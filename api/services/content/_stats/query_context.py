"""Prepared flat-file query context for file stats service flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from services.ai_settings import (
    AiSettingsService,
    document_classification_config_fingerprint,
    document_extraction_config_fingerprint,
    expected_document_extraction_models_by_schema,
)

from .filters import FieldPredicate, FlatContentListFilters


class FlatContentStatsQueryContextServiceProtocol(Protocol):
    """Internal ContentStatsService surface needed to prepare flat-query state."""

    db: AsyncSession

    @staticmethod
    def _flat_file_filters(
        *,
        name_contains: str | None = None,
        name_regex: bool = False,
        search_path: bool = False,
        content_kind: str | None = None,
        extension: str | None = None,
        status: str | None = None,
        document_class: str | None = None,
        extraction_schema: str | None = None,
        extraction_field: str | None = None,
        extraction_value: str | None = None,
        extraction_value_number_min: float | None = None,
        extraction_value_number_max: float | None = None,
        extraction_value_date_from: date | None = None,
        extraction_value_date_to: date | None = None,
        field_predicates: tuple[FieldPredicate, ...] = (),
        review_status: str | None = None,
        review_reason: str | None = None,
        needs_review: bool = False,
        stale_enrichment: bool = False,
        classification_enabled: bool = False,
        extraction_enabled: bool = False,
        classification_fingerprint: str = "",
        extraction_fingerprint: str = "",
        extraction_model: str = "",
        extraction_schema_models: dict[str, str] | None = None,
    ) -> FlatContentListFilters: ...


@dataclass(slots=True)
class FlatContentQueryContext:
    """Prepared settings and normalized filters for one flat-file query."""

    effective_settings: Any
    flat_filters: FlatContentListFilters


class FlatContentQueryContextBuilder:
    """Build reusable query context for flat-file listing and queue flows."""

    @classmethod
    async def build(
        cls,
        service: FlatContentStatsQueryContextServiceProtocol,
        *,
        name_contains: str | None = None,
        name_regex: bool = False,
        search_path: bool = False,
        content_kind: str | None = None,
        extension: str | None = None,
        status: str | None = None,
        document_class: str | None = None,
        extraction_schema: str | None = None,
        extraction_field: str | None = None,
        extraction_value: str | None = None,
        extraction_value_number_min: float | None = None,
        extraction_value_number_max: float | None = None,
        extraction_value_date_from: date | None = None,
        extraction_value_date_to: date | None = None,
        field_predicates: tuple[FieldPredicate, ...] = (),
        review_status: str | None = None,
        review_reason: str | None = None,
        needs_review: bool = False,
        stale_enrichment: bool = False,
    ) -> FlatContentQueryContext:
        """Prepare effective settings and normalized flat filters once."""
        effective_settings = await AiSettingsService(
            service.db
        ).get_effective_settings()
        classification_fingerprint = document_classification_config_fingerprint(
            effective_settings
        )
        extraction_fingerprint = document_extraction_config_fingerprint(
            effective_settings
        )
        flat_filters = service._flat_file_filters(
            name_contains=name_contains,
            name_regex=name_regex,
            search_path=search_path,
            content_kind=content_kind,
            extension=extension,
            status=status,
            document_class=document_class,
            extraction_schema=extraction_schema,
            extraction_field=extraction_field,
            extraction_value=extraction_value,
            extraction_value_number_min=extraction_value_number_min,
            extraction_value_number_max=extraction_value_number_max,
            extraction_value_date_from=extraction_value_date_from,
            extraction_value_date_to=extraction_value_date_to,
            field_predicates=field_predicates,
            review_status=review_status,
            review_reason=review_reason,
            needs_review=needs_review,
            stale_enrichment=stale_enrichment,
            classification_enabled=effective_settings.document_classification_enabled,
            extraction_enabled=effective_settings.document_extraction_enabled,
            classification_fingerprint=classification_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
            extraction_model=effective_settings.document_extraction_model,
            extraction_schema_models=expected_document_extraction_models_by_schema(
                effective_settings
            ),
        )
        return FlatContentQueryContext(
            effective_settings=effective_settings,
            flat_filters=flat_filters,
        )
