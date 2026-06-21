"""Unit tests for the field-example candidate service."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.content.enrichment import (
    ContentEnrichmentFieldExampleService,
    UnknownFieldError,
    UnknownSchemaError,
)


def _state(
    *,
    content_item_id: str,
    relative_path: str,
    fields_json: dict,
    review_status: str | None = "accepted",
    updated_at: datetime | None = None,
):
    state = SimpleNamespace(
        content_item_id=content_item_id,
        extraction_review_status=review_status,
        extraction_fields_json=fields_json,
        updated_at=updated_at or datetime(2026, 5, 15, 12, 0, 0),
        content_item=SimpleNamespace(relative_path=relative_path),
    )
    return state


def _schema_row(*, name: str, fields: list[dict]):
    return SimpleNamespace(name=name, fields_json=fields)


def _execute_results(*results) -> MagicMock:
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    return db


def _scalar_one_or_none(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(values) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


def _rows_all(rows) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_suggest_candidates_returns_grounded_scalar_value():
    schema_row = _schema_row(
        name="invoice_fields",
        fields=[
            {"name": "invoice_number", "dtype": "str", "description": "Invoice number"}
        ],
    )
    state = _state(
        content_item_id="file-1",
        relative_path="docs/invoice.pdf",
        fields_json={
            "invoice_number": {
                "value": "4711",
                "evidence": [
                    {"chunk_index": 2, "page_numbers": [1]},
                ],
            }
        },
    )
    db = _execute_results(
        _scalar_one_or_none(schema_row),
        _scalars_all([state]),
        _rows_all([("file-1", 2, "Invoice No. 4711 issued on 2026-05-15.")]),
    )

    response = await ContentEnrichmentFieldExampleService(db).suggest_candidates(
        schema_name="invoice_fields",
        field_name="invoice_number",
        content_item_ids=["file-1"],
    )

    assert len(response.candidates) == 1
    candidate = response.candidates[0]
    assert candidate.value == "4711"
    assert candidate.anchor_text == "4711"
    assert candidate.text.startswith("Invoice No. 4711")
    assert candidate.page_numbers == [1]
    assert candidate.chunk_index == 2
    assert candidate.review_status == "accepted"


@pytest.mark.asyncio
async def test_suggest_candidates_dedupes_by_value_across_reviewed_files():
    schema_row = _schema_row(
        name="invoice_fields",
        fields=[{"name": "vendor", "dtype": "str", "description": "Vendor"}],
    )
    state_a = _state(
        content_item_id="file-a",
        relative_path="docs/a.pdf",
        fields_json={
            "vendor": {
                "value": "Acme GmbH",
                "evidence": [{"chunk_index": 0}],
            }
        },
        updated_at=datetime(2026, 5, 15, 9, 0, 0),
    )
    state_b = _state(
        content_item_id="file-b",
        relative_path="docs/b.pdf",
        fields_json={
            "vendor": {
                "value": "Acme GmbH",
                "evidence": [{"chunk_index": 0}],
            }
        },
        review_status="corrected",
        updated_at=datetime(2026, 5, 15, 12, 0, 0),
    )
    db = _execute_results(
        _scalar_one_or_none(schema_row),
        _scalars_all([state_a, state_b]),
        _rows_all(
            [
                ("file-a", 0, "Vendor: Acme GmbH on the invoice header."),
                ("file-b", 0, "Vendor: Acme GmbH on the invoice header."),
            ]
        ),
    )

    response = await ContentEnrichmentFieldExampleService(db).suggest_candidates(
        schema_name="invoice_fields",
        field_name="vendor",
        content_item_ids=["file-a", "file-b"],
    )

    # Same value → one candidate. Most-recently-updated reviewed state wins.
    assert len(response.candidates) == 1
    assert response.candidates[0].content_item_id == "file-b"
    assert response.candidates[0].review_status == "corrected"


@pytest.mark.asyncio
async def test_suggest_candidates_emits_one_row_per_object_list_entry():
    schema_row = _schema_row(
        name="task_schema",
        fields=[
            {
                "name": "tasks",
                "dtype": "object_list",
                "description": "Tasks",
                "fields": [{"name": "title", "dtype": "str", "description": "Title"}],
            }
        ],
    )
    state = _state(
        content_item_id="file-1",
        relative_path="docs/task.pdf",
        fields_json={
            "tasks": {
                "value": [
                    {"title": "Submit the report"},
                    {"title": "Update the budget"},
                ],
                "evidence": [
                    {"chunk_index": 5},
                    {"chunk_index": 7},
                ],
            }
        },
    )
    db = _execute_results(
        _scalar_one_or_none(schema_row),
        _scalars_all([state]),
        _rows_all(
            [
                ("file-1", 5, "Action: Submit the report by Friday."),
                ("file-1", 7, "Action: Update the budget for Q3."),
            ]
        ),
    )

    response = await ContentEnrichmentFieldExampleService(db).suggest_candidates(
        schema_name="task_schema",
        field_name="tasks",
        content_item_ids=["file-1"],
    )

    assert len(response.candidates) == 2
    values = [c.value for c in response.candidates]
    assert {"title": "Submit the report"} in values
    assert {"title": "Update the budget"} in values


@pytest.mark.asyncio
async def test_suggest_candidates_skips_when_value_not_in_chunk_text():
    schema_row = _schema_row(
        name="invoice_fields",
        fields=[{"name": "due_date", "dtype": "date", "description": "Due date"}],
    )
    state = _state(
        content_item_id="file-1",
        relative_path="docs/invoice.pdf",
        fields_json={
            "due_date": {
                # Normalized value that does not appear literally in the chunk text.
                "value": "2026-05-15",
                "evidence": [{"chunk_index": 0}],
            }
        },
    )
    db = _execute_results(
        _scalar_one_or_none(schema_row),
        _scalars_all([state]),
        _rows_all([("file-1", 0, "Due date is 15.05.2026.")]),
    )

    response = await ContentEnrichmentFieldExampleService(db).suggest_candidates(
        schema_name="invoice_fields",
        field_name="due_date",
        content_item_ids=["file-1"],
    )

    assert response.candidates == []


@pytest.mark.asyncio
async def test_suggest_candidates_raises_for_unknown_schema():
    db = _execute_results(_scalar_one_or_none(None))

    with pytest.raises(UnknownSchemaError):
        await ContentEnrichmentFieldExampleService(db).suggest_candidates(
            schema_name="missing",
            field_name="x",
            content_item_ids=["f"],
        )


@pytest.mark.asyncio
async def test_suggest_candidates_raises_for_unknown_field():
    schema_row = _schema_row(
        name="invoice_fields",
        fields=[
            {"name": "invoice_number", "dtype": "str", "description": "Invoice number"}
        ],
    )
    db = _execute_results(_scalar_one_or_none(schema_row))

    with pytest.raises(UnknownFieldError):
        await ContentEnrichmentFieldExampleService(db).suggest_candidates(
            schema_name="invoice_fields",
            field_name="not_a_field",
            content_item_ids=["f"],
        )


def test_reviewed_statuses_constant_excludes_unreviewed():
    """The SQL filter must accept only review-state values that imply human verification."""
    from services.content.enrichment.field_examples import _REVIEWED_STATUSES

    assert set(_REVIEWED_STATUSES) == {"accepted", "corrected"}
    assert "unreviewed" not in _REVIEWED_STATUSES


@pytest.mark.asyncio
async def test_suggest_candidates_returns_empty_for_empty_id_list():
    db = _execute_results(
        _scalar_one_or_none(
            _schema_row(
                name="s", fields=[{"name": "f", "dtype": "str", "description": "x"}]
            )
        ),
    )
    response = await ContentEnrichmentFieldExampleService(db).suggest_candidates(
        schema_name="s",
        field_name="f",
        content_item_ids=[],
    )
    assert response.candidates == []
