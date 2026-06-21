"""Focused tests for flat file listing assembly helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.future import select

from models.content.items import (
    ExtractionFieldFacet,
    ExtractionSchemaFieldFacet,
    ExtractionValueFacet,
    ReviewQueueSummary,
)
from models.sqlalchemy_models import IndexedContentItem
from services.content._stats.filters import FlatContentListFilters
from services.content._stats.listing import FlatContentListingAssembler


def _scalar_result(value: int):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _rows_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalars_result(rows):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def _build_service():
    service = MagicMock()
    service.db = MagicMock()
    service._flat_file_base_stmt.return_value = select(IndexedContentItem)
    service._apply_flat_filters.side_effect = lambda stmt, *, filters: stmt
    service._apply_flat_sort.side_effect = lambda stmt, *, sort_by, sort_order: stmt
    service._build_document_class_facet_stmt.return_value = object()
    service._build_extraction_schema_facet_stmt.return_value = object()
    service._build_extraction_schema_field_facet_stmt.return_value = object()
    service._build_extraction_field_facet_stmt.return_value = object()
    service._build_extraction_value_facet_stmt.return_value = object()
    service._collect_extraction_schema_field_facets.return_value = [
        ExtractionSchemaFieldFacet(
            field="invoice_number",
            dtype="str",
            description="Invoice number",
            required=True,
            count=2,
            total=3,
        )
    ]
    service._collect_extraction_field_facets.return_value = [
        ExtractionFieldFacet(field="invoice_number", count=2)
    ]
    service._collect_extraction_value_facets.return_value = [
        ExtractionValueFacet(value="RE-2026", count=2)
    ]
    service._collect_review_reason_facets = AsyncMock(return_value=[])
    service._collect_review_summary = AsyncMock(
        return_value=ReviewQueueSummary(
            total=10,
            unreviewed=4,
            accepted=2,
            corrected=1,
            needs_review=3,
            missing_required_fields=2,
            conflicted_fields=1,
            missing_evidence=1,
        )
    )
    service._to_file_infos = AsyncMock(return_value=[])
    return service


@pytest.mark.asyncio
async def test_listing_assembler_collects_schema_and_value_facets_when_requested():
    """Listing assembly should include schema coverage and value facets when scoped."""
    service = _build_service()
    service._find_configured_extraction_schema.return_value = object()
    service.db.execute = AsyncMock(
        side_effect=[
            _scalar_result(10),
            _rows_result([("invoice", 4)]),
            _rows_result([("invoice_fields", 4)]),
            _rows_result([({"data": {"invoice_number": "RE-1"}}, None)]),
            _rows_result([({"data": {"invoice_number": "RE-1"}}, None)]),
            _rows_result([({"data": {"invoice_number": "RE-1"}}, None)]),
            _scalars_result([]),
        ]
    )

    response = await FlatContentListingAssembler(
        service=service,
        user=None,
        effective_settings=SimpleNamespace(document_extraction_schemas=["ignored"]),
        flat_filters=FlatContentListFilters(
            extraction_schema="invoice_fields",
            extraction_field=" invoice_number ",
        ),
        extraction_schema="invoice_fields",
        limit=25,
        offset=0,
        sort_by="name",
        sort_order="asc",
    ).build_response()

    assert response.total == 10
    assert response.document_class_facets[0].label == "invoice"
    assert response.extraction_schema_facets[0].schema_name == "invoice_fields"
    assert response.extraction_schema_field_facets[0].field == "invoice_number"
    assert response.extraction_field_facets[0].field == "invoice_number"
    assert response.extraction_value_facets[0].value == "RE-2026"
    service._build_extraction_schema_field_facet_stmt.assert_called_once()
    service._build_extraction_value_facet_stmt.assert_called_once_with(
        user=None,
        filters=FlatContentListFilters(
            extraction_schema="invoice_fields",
            extraction_field=" invoice_number ",
        ),
        extraction_field="invoice_number",
    )


@pytest.mark.asyncio
async def test_listing_assembler_skips_optional_schema_and_value_facets_when_unscoped():
    """Listing assembly should skip optional facet queries when no schema or field is active."""
    service = _build_service()
    service._find_configured_extraction_schema.return_value = None
    service.db.execute = AsyncMock(
        side_effect=[
            _scalar_result(5),
            _rows_result([]),
            _rows_result([]),
            _rows_result([]),
            _scalars_result([]),
        ]
    )

    response = await FlatContentListingAssembler(
        service=service,
        user=None,
        effective_settings=SimpleNamespace(document_extraction_schemas=[]),
        flat_filters=FlatContentListFilters(),
        extraction_schema=None,
        limit=25,
        offset=0,
        sort_by="name",
        sort_order="asc",
    ).build_response()

    assert response.total == 5
    assert response.extraction_schema_field_facets == []
    assert response.extraction_value_facets == []
    service._build_extraction_schema_field_facet_stmt.assert_not_called()
    service._build_extraction_value_facet_stmt.assert_not_called()
