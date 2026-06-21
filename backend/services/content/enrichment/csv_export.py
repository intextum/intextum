"""CSV export helpers for effective extracted content data."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from io import StringIO
from typing import Any, Callable, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import IndexedContentItem
from models.user import User
from services.content.location import render_api_path
from services.utils import find_folder_by_uuid

from .._stats.filters import (
    FieldPredicate,
    FlatContentListFilters,
    scope_filters_to_path,
)
from .._stats.query_context import FlatContentQueryContextBuilder


FIXED_EXTRACTED_DATA_CSV_COLUMNS = [
    "content_item_id",
    "path",
    "display_name",
    "document_class",
    "extraction_schema",
    "extraction_review_status",
    "processed_at",
]


class ExtractedDataCsvServiceProtocol(Protocol):
    """ContentStatsService surface needed to export filtered extracted data."""

    db: AsyncSession

    @staticmethod
    def _flat_file_base_stmt(): ...

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

    @staticmethod
    def _apply_flat_filters(stmt, *, filters: FlatContentListFilters): ...

    @staticmethod
    def _apply_flat_sort(stmt, *, sort_by: str, sort_order: str): ...


@dataclass(slots=True)
class ExtractedDataCsvRow:
    """One normalized CSV export row before final header projection."""

    metadata: dict[str, Any]
    data: dict[str, Any]


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _cell_value(value: Any) -> str:
    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int | float):
        text = str(value)
    elif isinstance(value, list | dict):
        text = _json_cell(value)
    else:
        text = str(value)

    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _iso_datetime(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else ""


def _field_names_for_schema(settings: Any, extraction_schema: str | None) -> list[str]:
    normalized_schema = extraction_schema.strip().lower() if extraction_schema else ""
    if not normalized_schema:
        return []

    schemas = getattr(settings, "document_extraction_schemas", []) or []
    exact_match = None
    fuzzy_match = None
    for schema in schemas:
        schema_name = getattr(schema, "name", "")
        normalized_name = (
            schema_name.strip().lower() if isinstance(schema_name, str) else ""
        )
        if not normalized_name:
            continue
        if normalized_name == normalized_schema:
            exact_match = schema
            break
        if normalized_schema in normalized_name and fuzzy_match is None:
            fuzzy_match = schema

    schema = exact_match or fuzzy_match
    if schema is None:
        return []
    return [
        field.name
        for field in getattr(schema, "fields", []) or []
        if isinstance(getattr(field, "name", None), str) and field.name.strip()
    ]


def _api_path_for_row(
    row: IndexedContentItem,
    folder_resolver: Callable[[str], Any | None],
) -> str | None:
    folder = folder_resolver(row.folder_uuid)
    if folder is None:
        return None
    return render_api_path(folder, row.relative_path)


def _csv_rows_from_records(
    records: list[IndexedContentItem],
    *,
    folder_resolver: Callable[[str], Any | None],
) -> list[ExtractedDataCsvRow]:
    csv_rows: list[ExtractedDataCsvRow] = []
    for record in records:
        path = _api_path_for_row(record, folder_resolver)
        if path is None:
            continue

        state = record.enrichment_state
        extraction_data = (
            _dict_value(state.extraction_effective_data_json)
            if state is not None
            else {}
        )
        csv_rows.append(
            ExtractedDataCsvRow(
                metadata={
                    "content_item_id": record.content_item_id,
                    "path": path,
                    "display_name": record.display_name or record.name,
                    "document_class": (
                        (
                            state.extraction_effective_class_label
                            or state.classification_effective_label
                        )
                        if state is not None
                        else ""
                    ),
                    "extraction_schema": (
                        (
                            state.extraction_effective_schema_name
                            or state.extraction_system_schema_name
                        )
                        if state is not None
                        else ""
                    ),
                    "extraction_review_status": (
                        state.extraction_review_status if state is not None else ""
                    ),
                    "processed_at": _iso_datetime(record.processed_at),
                },
                data=extraction_data,
            )
        )
    return csv_rows


def _field_columns(
    rows: list[ExtractedDataCsvRow],
    *,
    configured_fields: list[str],
) -> list[str]:
    discovered_fields = {
        key for row in rows for key in row.data if isinstance(key, str) and key.strip()
    }
    if not configured_fields:
        return sorted(discovered_fields)

    configured = list(dict.fromkeys(configured_fields))
    extra = sorted(discovered_fields.difference(configured_fields))
    return configured + extra


def render_extracted_data_csv(
    rows: list[ExtractedDataCsvRow],
    *,
    configured_fields: list[str] | None = None,
) -> str:
    """Render normalized extracted data rows as wide CSV."""
    field_columns = _field_columns(rows, configured_fields=configured_fields or [])
    headers = FIXED_EXTRACTED_DATA_CSV_COLUMNS + field_columns
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(
            [
                _cell_value(row.metadata.get(column))
                for column in FIXED_EXTRACTED_DATA_CSV_COLUMNS
            ]
            + [_cell_value(row.data.get(column)) for column in field_columns]
        )
    return output.getvalue()


async def build_extracted_data_csv(
    service: ExtractedDataCsvServiceProtocol,
    *,
    user: User | None,
    name_contains: str | None = None,
    name_regex: bool = False,
    search_path: bool = False,
    path: str | None = None,
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
    folder_resolver: Callable[[str], Any | None] = find_folder_by_uuid,
) -> str:
    """Build an extracted-data CSV for all rows matching the flat content filters."""
    _ = user
    query_context = await FlatContentQueryContextBuilder.build(
        service,
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
    )
    flat_filters = scope_filters_to_path(query_context.flat_filters, path)
    stmt = service._apply_flat_filters(
        service._flat_file_base_stmt(),
        filters=flat_filters,
    )
    stmt = service._apply_flat_sort(stmt, sort_by="name", sort_order="asc")
    records = (await service.db.execute(stmt)).unique().scalars().all()
    csv_rows = _csv_rows_from_records(
        list(records),
        folder_resolver=folder_resolver,
    )
    configured_fields = _field_names_for_schema(
        query_context.effective_settings,
        extraction_schema,
    )
    return render_extracted_data_csv(csv_rows, configured_fields=configured_fields)
