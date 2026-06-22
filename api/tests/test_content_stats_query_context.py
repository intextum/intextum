"""Focused tests for shared flat-file query context preparation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.content._stats.filters import FlatContentListFilters
from services.content._stats.query_context import FlatContentQueryContextBuilder


@pytest.mark.asyncio
async def test_query_context_builder_threads_effective_settings():
    """Query context should normalize the shared filter prelude once."""
    service = MagicMock()
    service.db = MagicMock()
    service._flat_file_filters.return_value = FlatContentListFilters(
        document_class="invoice",
    )
    effective_settings = SimpleNamespace(
        document_classification_enabled=True,
        document_extraction_enabled=True,
        document_extraction_model="registry:global-extract",
        document_extraction_llm_model="registry:llm-extract",
        document_extraction_schema_models={"invoice_fields": "registry:invoice-v2"},
        document_extraction_schemas=[
            SimpleNamespace(name="invoice_fields", fields=[]),
        ],
    )

    with (
        patch(
            "services.content._stats.query_context.AiSettingsService"
        ) as ai_settings_service_cls,
        patch(
            "services.content._stats.query_context.document_classification_config_fingerprint",
            return_value="class-fingerprint",
        ),
        patch(
            "services.content._stats.query_context.document_extraction_config_fingerprint",
            return_value="extract-fingerprint",
        ),
    ):
        ai_settings_service_cls.return_value.get_effective_settings = AsyncMock(
            return_value=effective_settings
        )

        query_context = await FlatContentQueryContextBuilder.build(
            service,
            document_class="invoice",
        )

    assert query_context.effective_settings is effective_settings
    assert query_context.flat_filters.document_class == "invoice"
    service._flat_file_filters.assert_called_once_with(
        name_contains=None,
        name_regex=False,
        search_path=False,
        ids=None,
        content_kind=None,
        extension=None,
        status=None,
        document_class="invoice",
        extraction_schema=None,
        extraction_field=None,
        extraction_value=None,
        extraction_value_number_min=None,
        extraction_value_number_max=None,
        extraction_value_date_from=None,
        extraction_value_date_to=None,
        field_predicates=(),
        review_status=None,
        review_reason=None,
        needs_review=False,
        stale_enrichment=False,
        classification_enabled=True,
        extraction_enabled=True,
        classification_fingerprint="class-fingerprint",
        extraction_fingerprint="extract-fingerprint",
        extraction_model="registry:global-extract",
        extraction_schema_models={"invoice_fields": "registry:invoice-v2"},
    )
