"""Tests for extracted-data CSV export helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.content.enrichment.csv_export import (
    ExtractedDataCsvRow,
    build_extracted_data_csv,
    render_extracted_data_csv,
)


def test_render_extracted_data_csv_handles_wide_rows_and_protects_formula_values():
    csv_text = render_extracted_data_csv(
        [
            ExtractedDataCsvRow(
                metadata={
                    "content_item_id": "item-1",
                    "path": "docs/invoice.pdf",
                    "display_name": "Invoice",
                    "document_class": "Invoice",
                    "extraction_schema": "invoice_fields",
                    "extraction_review_status": "corrected",
                    "processed_at": "2026-06-03T12:00:00",
                },
                data={
                    "amount": 12.5,
                    "formula": '=HYPERLINK("https://example.invalid")',
                    "line_items": [{"name": "A", "qty": 2}],
                    "paid": True,
                },
            )
        ],
        configured_fields=["formula", "amount", "paid", "line_items"],
    )

    assert csv_text.splitlines()[0] == (
        "content_item_id,path,display_name,document_class,extraction_schema,"
        "extraction_review_status,processed_at,formula,amount,paid,line_items"
    )
    assert "'=HYPERLINK" in csv_text
    assert "12.5" in csv_text
    assert "true" in csv_text
    assert """[{""name"":""A"",""qty"":2}]""" in csv_text


def test_render_extracted_data_csv_returns_header_only_when_no_rows_match():
    csv_text = render_extracted_data_csv([], configured_fields=[])

    assert csv_text == (
        "content_item_id,path,display_name,document_class,extraction_schema,"
        "extraction_review_status,processed_at\r\n"
    )


@pytest.mark.asyncio
async def test_build_extracted_data_csv_uses_effective_data_and_matching_filters():
    flat_filters = SimpleNamespace()
    settings = SimpleNamespace(
        document_extraction_schemas=[
            SimpleNamespace(
                name="invoice_fields",
                fields=[
                    SimpleNamespace(name="invoice_number"),
                    SimpleNamespace(name="amount"),
                ],
            )
        ]
    )
    state = SimpleNamespace(
        extraction_effective_data_json={
            "invoice_number": "RE-1",
            "amount": 42,
            "corrected_extra": "@reviewed",
        },
        extraction_effective_class_label="Invoice",
        classification_effective_label="Other",
        extraction_effective_schema_name="invoice_fields",
        extraction_system_schema_name="invoice_fields",
        extraction_review_status="corrected",
    )
    record = SimpleNamespace(
        content_item_id="item-1",
        folder_uuid="folder-1",
        relative_path="invoices/re-1.pdf",
        display_name="RE-1.pdf",
        name="re-1.pdf",
        processed_at=SimpleNamespace(isoformat=lambda: "2026-06-03T12:00:00"),
        enrichment_state=state,
    )
    result = MagicMock()
    result.unique.return_value.scalars.return_value.all.return_value = [record]
    service = SimpleNamespace(
        db=SimpleNamespace(execute=AsyncMock(return_value=result)),
        _flat_file_base_stmt=MagicMock(return_value="base"),
        _apply_flat_filters=MagicMock(return_value="filtered"),
        _apply_flat_sort=MagicMock(return_value="sorted"),
        _flat_file_filters=MagicMock(return_value=flat_filters),
    )

    with patch(
        "services.content.enrichment.csv_export.FlatContentQueryContextBuilder.build",
        new=AsyncMock(
            return_value=SimpleNamespace(
                effective_settings=settings,
                flat_filters=flat_filters,
            )
        ),
    ) as build_context:
        csv_text = await build_extracted_data_csv(
            service,
            user=SimpleNamespace(),
            document_class="Invoice",
            extraction_schema="invoice_fields",
            review_status="corrected",
            folder_resolver=lambda _folder_uuid: SimpleNamespace(name="Documents"),
        )

    build_context.assert_awaited_once()
    assert build_context.await_args.kwargs["document_class"] == "Invoice"
    assert build_context.await_args.kwargs["extraction_schema"] == "invoice_fields"
    assert build_context.await_args.kwargs["review_status"] == "corrected"
    service._apply_flat_filters.assert_called_once_with("base", filters=flat_filters)
    service._apply_flat_sort.assert_called_once_with(
        "filtered", sort_by="name", sort_order="asc"
    )
    header = csv_text.splitlines()[0]
    assert header.endswith(",invoice_number,amount,corrected_extra")
    assert "Documents/invoices/re-1.pdf" in csv_text
    assert "Invoice" in csv_text
    assert "corrected" in csv_text
    assert "RE-1" in csv_text
    assert "'@reviewed" in csv_text
