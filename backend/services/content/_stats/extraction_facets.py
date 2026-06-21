"""Extraction facet expressions and collectors for flat file stats."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Date, Float, case, cast, desc, func, select

from models.ai_settings import (
    DocumentExtractionChildField,
    DocumentExtractionField,
    DocumentExtractionSchema,
)
from models.content.items import (
    DocumentClassFacet,
    ExtractionFieldFacet,
    ExtractionSchemaFacet,
    ExtractionSchemaFieldFacet,
    ExtractionValueFacet,
)
from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem
from models.user import User

from ..enrichment import query_expressions
from .filters import FlatContentListFilters


@dataclass(frozen=True)
class _Leaf:
    """One comparable leaf path derived from a configured extraction field."""

    label: str
    segments: list[dict[str, Any]]
    dtype: str
    description: str
    required: bool


def _scalar_leaves(
    *,
    label: str,
    base: list[dict[str, Any]],
    dtype: str,
    description: str,
    required: bool,
) -> list[_Leaf]:
    """Expand one scalar/currency/list value into its comparable leaves."""
    if dtype == "currency":
        return [
            _Leaf(
                f"{label}.amount",
                base + [{"k": "amount"}],
                "float",
                description,
                required,
            ),
            _Leaf(
                f"{label}.currency",
                base + [{"k": "currency"}],
                "str",
                description,
                False,
            ),
        ]
    if dtype == "list":
        return [
            _Leaf(f"{label}[]", base + [{"elem": True}], "str", description, required)
        ]
    return [_Leaf(label, base, dtype, description, required)]


def _enumerate_field_leaves(field: DocumentExtractionField) -> list[_Leaf]:
    """Yield comparable leaves for one top-level configured field."""
    base = [{"k": field.name}]
    if field.dtype == "object_list":
        leaves: list[_Leaf] = []
        element_base = base + [{"elem": True}]
        child: DocumentExtractionChildField
        for child in field.fields:
            leaves.extend(
                _scalar_leaves(
                    label=f"{field.name}[].{child.name}",
                    base=element_base + [{"k": child.name}],
                    dtype=child.dtype,
                    description=child.description,
                    required=child.required,
                )
            )
        return leaves
    return _scalar_leaves(
        label=field.name,
        base=base,
        dtype=field.dtype,
        description=field.description,
        required=field.required,
    )


class ExtractionFacetHelpers:
    """Shared extraction facet builders and collectors."""

    @staticmethod
    def effective_document_class_expr():
        """Return the effective document class."""
        return query_expressions.effective_document_class_expr()

    @staticmethod
    def effective_extraction_schema_expr():
        """Return the effective extraction schema."""
        return query_expressions.effective_extraction_schema_expr()

    @staticmethod
    def effective_extraction_field_expr(field_name: str):
        """Return one effective extraction field expression."""
        return query_expressions.effective_extraction_field_expr(field_name)

    @classmethod
    def numeric_extraction_field_expr(cls, field_name: str):
        """Return one numeric extraction field expression when the value parses cleanly."""
        field_expr = cls.effective_extraction_field_expr(field_name)
        return case(
            (
                field_expr.op("~")(r"^\s*-?(?:\d+(?:\.\d+)?|\.\d+)\s*$"),
                cast(field_expr, Float),
            ),
            else_=None,
        )

    @classmethod
    def date_extraction_field_expr(cls, field_name: str):
        """Return one ISO date extraction field expression when the value parses cleanly."""
        date_prefix = func.substr(
            cls.effective_extraction_field_expr(field_name), 1, 10
        )
        return case(
            (
                date_prefix.op("~")(r"^\d{4}-\d{2}-\d{2}$"),
                cast(date_prefix, Date),
            ),
            else_=None,
        )

    @classmethod
    def build_document_class_facet_stmt(cls, stmt):
        """Build the grouped facet statement for effective document classes."""
        facet_expr = cls.effective_document_class_expr().label("document_class")
        return (
            stmt.with_only_columns(facet_expr, func.count())
            .where(facet_expr.is_not(None))
            .group_by(facet_expr)
            .order_by(desc(func.count()), facet_expr)
        )

    @classmethod
    def build_extraction_schema_facet_stmt(cls, stmt):
        """Build the grouped facet statement for effective extraction schemas."""
        facet_expr = cls.effective_extraction_schema_expr().label("extraction_schema")
        return (
            stmt.with_only_columns(facet_expr, func.count())
            .where(facet_expr.is_not(None))
            .group_by(facet_expr)
            .order_by(desc(func.count()), facet_expr)
        )

    @classmethod
    def build_extraction_field_facet_stmt(
        cls,
        *,
        user: User | None,
        filters: FlatContentListFilters | None = None,
        name_contains: str | None = None,
        name_regex: bool = False,
        search_path: bool = False,
        extension: str | None = None,
        status: str | None = None,
        document_class: str | None = None,
        extraction_schema: str | None = None,
        extraction_value: str | None = None,
        extraction_value_number_min: float | None = None,
        extraction_value_number_max: float | None = None,
        extraction_value_date_from: date | None = None,
        extraction_value_date_to: date | None = None,
        review_status: str | None = None,
        review_reason: str | None = None,
        needs_review: bool = False,
        stale_enrichment: bool = False,
        classification_enabled: bool = False,
        extraction_enabled: bool = False,
        classification_fingerprint: str = "",
        extraction_fingerprint: str = "",
        flat_file_filters_builder=None,
        apply_filters=None,
    ):
        """Build the source statement for extraction field facets."""
        if flat_file_filters_builder is None or apply_filters is None:
            raise ValueError("Facet builder callbacks must be provided")
        flat_filters = filters or flat_file_filters_builder(
            name_contains=name_contains,
            name_regex=name_regex,
            search_path=search_path,
            extension=extension,
            status=status,
            document_class=document_class,
            extraction_schema=extraction_schema,
            extraction_value=extraction_value,
            extraction_value_number_min=extraction_value_number_min,
            extraction_value_number_max=extraction_value_number_max,
            extraction_value_date_from=extraction_value_date_from,
            extraction_value_date_to=extraction_value_date_to,
            review_status=review_status,
            review_reason=review_reason,
            needs_review=needs_review,
            stale_enrichment=stale_enrichment,
            classification_enabled=classification_enabled,
            extraction_enabled=extraction_enabled,
            classification_fingerprint=classification_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
        )
        stmt = (
            select(
                ContentItemEnrichmentState.extraction_effective_data_json,
            )
            .select_from(IndexedContentItem)
            .join(ContentItemEnrichmentState)
            .where(
                IndexedContentItem.is_dir.is_(False),
                IndexedContentItem.is_hidden.is_(False),
            )
        )
        return apply_filters(stmt, filters=flat_filters.for_extraction_field_facets())

    @classmethod
    def build_extraction_schema_field_facet_stmt(
        cls,
        *,
        user: User | None,
        filters: FlatContentListFilters | None = None,
        name_contains: str | None = None,
        name_regex: bool = False,
        search_path: bool = False,
        extension: str | None = None,
        status: str | None = None,
        document_class: str | None = None,
        extraction_schema: str | None = None,
        review_status: str | None = None,
        review_reason: str | None = None,
        needs_review: bool = False,
        stale_enrichment: bool = False,
        classification_enabled: bool = False,
        extraction_enabled: bool = False,
        classification_fingerprint: str = "",
        extraction_fingerprint: str = "",
        flat_file_filters_builder=None,
        apply_filters=None,
    ):
        """Build the source statement for extraction schema field coverage facets."""
        if flat_file_filters_builder is None or apply_filters is None:
            raise ValueError("Facet builder callbacks must be provided")
        flat_filters = filters or flat_file_filters_builder(
            name_contains=name_contains,
            name_regex=name_regex,
            search_path=search_path,
            extension=extension,
            status=status,
            document_class=document_class,
            extraction_schema=extraction_schema,
            review_status=review_status,
            review_reason=review_reason,
            needs_review=needs_review,
            stale_enrichment=stale_enrichment,
            classification_enabled=classification_enabled,
            extraction_enabled=extraction_enabled,
            classification_fingerprint=classification_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
        )
        stmt = (
            select(
                ContentItemEnrichmentState.extraction_effective_data_json,
            )
            .select_from(IndexedContentItem)
            .join(ContentItemEnrichmentState)
            .where(
                IndexedContentItem.is_dir.is_(False),
                IndexedContentItem.is_hidden.is_(False),
            )
        )
        return apply_filters(
            stmt,
            filters=flat_filters.for_extraction_schema_field_facets(),
        )

    @classmethod
    def build_extraction_value_facet_stmt(
        cls,
        *,
        user: User | None,
        filters: FlatContentListFilters | None = None,
        name_contains: str | None = None,
        name_regex: bool = False,
        search_path: bool = False,
        extension: str | None = None,
        status: str | None = None,
        document_class: str | None = None,
        extraction_schema: str | None = None,
        extraction_field: str,
        extraction_value_number_min: float | None = None,
        extraction_value_number_max: float | None = None,
        extraction_value_date_from: date | None = None,
        extraction_value_date_to: date | None = None,
        review_status: str | None = None,
        review_reason: str | None = None,
        needs_review: bool = False,
        stale_enrichment: bool = False,
        classification_enabled: bool = False,
        extraction_enabled: bool = False,
        classification_fingerprint: str = "",
        extraction_fingerprint: str = "",
        flat_file_filters_builder=None,
        apply_filters=None,
    ):
        """Build the source statement for extraction value facets."""
        if flat_file_filters_builder is None or apply_filters is None:
            raise ValueError("Facet builder callbacks must be provided")
        flat_filters = filters or flat_file_filters_builder(
            name_contains=name_contains,
            name_regex=name_regex,
            search_path=search_path,
            extension=extension,
            status=status,
            document_class=document_class,
            extraction_schema=extraction_schema,
            extraction_field=extraction_field,
            extraction_value_number_min=extraction_value_number_min,
            extraction_value_number_max=extraction_value_number_max,
            extraction_value_date_from=extraction_value_date_from,
            extraction_value_date_to=extraction_value_date_to,
            review_status=review_status,
            review_reason=review_reason,
            needs_review=needs_review,
            stale_enrichment=stale_enrichment,
            classification_enabled=classification_enabled,
            extraction_enabled=extraction_enabled,
            classification_fingerprint=classification_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
        )
        stmt = (
            select(
                ContentItemEnrichmentState.extraction_effective_data_json,
            )
            .select_from(IndexedContentItem)
            .join(ContentItemEnrichmentState)
            .where(
                IndexedContentItem.is_dir.is_(False),
                IndexedContentItem.is_hidden.is_(False),
            )
        )
        stmt = apply_filters(stmt, filters=flat_filters.for_extraction_value_facets())
        return stmt.where(
            cls.effective_extraction_field_expr(extraction_field).is_not(None)
        )

    @classmethod
    def collect_extraction_field_facets(
        cls,
        rows: list[tuple[dict[str, Any] | None]],
        limit: int = 8,
    ) -> list[ExtractionFieldFacet]:
        """Collect extraction field facet counts from effective row data."""
        counts: Counter[str] = Counter()

        for (effective_data,) in rows:
            for key in cls.effective_extraction_field_keys(effective_data):
                counts[key] += 1

        return [
            ExtractionFieldFacet(field=field, count=count)
            for field, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:limit]
        ]

    @classmethod
    def collect_extraction_schema_field_facets(
        cls,
        rows: list[tuple[dict[str, Any] | None]],
        *,
        schemas: list[DocumentExtractionSchema],
    ) -> list[ExtractionSchemaFieldFacet]:
        """Collect filterable leaf paths across the given configured schemas.

        Each configured field expands into one or more comparable *leaves*:
        scalars map to themselves, ``currency`` to ``.amount``/``.currency``,
        ``list`` to its elements, and ``object_list`` to ``[].child`` leaves.
        Leaves are de-duplicated by label (first schema wins) so the picker stays
        typed even when no single schema is selected; coverage counts reflect
        presence of the top-level field across the result set.
        """
        if not rows or not schemas:
            return []

        total = len(rows)
        field_names: list[str] = []
        seen_field_names: set[str] = set()
        for schema in schemas:
            for field in schema.fields:
                if field.name not in seen_field_names:
                    seen_field_names.add(field.name)
                    field_names.append(field.name)

        counts: Counter[str] = Counter()
        for (effective_data,) in rows:
            for name in field_names:
                value = cls.effective_extraction_value_for_field(effective_data, name)
                if cls.has_meaningful_extraction_value(value):
                    counts[name] += 1

        facets: list[ExtractionSchemaFieldFacet] = []
        seen_labels: set[str] = set()
        for schema in schemas:
            for field in schema.fields:
                parent_count = counts.get(field.name, 0)
                for leaf in _enumerate_field_leaves(field):
                    if leaf.label in seen_labels:
                        continue
                    seen_labels.add(leaf.label)
                    facets.append(
                        ExtractionSchemaFieldFacet(
                            field=field.name,
                            label=leaf.label,
                            segments=leaf.segments,
                            dtype=leaf.dtype,
                            description=leaf.description,
                            required=leaf.required,
                            count=parent_count,
                            total=total,
                        )
                    )
        return facets

    @classmethod
    def collect_extraction_value_facets(
        cls,
        rows: list[tuple[dict[str, Any] | None]],
        *,
        field_name: str,
        limit: int = 8,
    ) -> list[ExtractionValueFacet]:
        """Collect extraction value facet counts from effective row data."""
        counts: Counter[str] = Counter()

        for (effective_data,) in rows:
            value = cls.effective_extraction_value_for_field(
                effective_data,
                field_name,
            )
            if not cls.has_meaningful_extraction_value(value):
                continue
            serialized = cls.stringify_extraction_facet_value(value)
            if not serialized:
                continue
            counts[serialized] += 1

        return [
            ExtractionValueFacet(value=value, count=count)
            for value, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:limit]
        ]

    @classmethod
    def effective_extraction_field_keys(
        cls,
        effective_data: dict[str, Any] | None,
    ) -> list[str]:
        """Return effective extraction data keys with meaningful values."""
        merged = dict(effective_data) if isinstance(effective_data, dict) else {}

        return [
            key
            for key, value in merged.items()
            if key.strip() and cls.has_meaningful_extraction_value(value)
        ]

    @staticmethod
    def find_configured_extraction_schema(
        schemas: list[DocumentExtractionSchema],
        raw_schema_name: str | None,
    ) -> DocumentExtractionSchema | None:
        """Find the configured extraction schema matching the requested name."""
        normalized_schema_name = (
            raw_schema_name.strip().lower() if raw_schema_name else ""
        )
        if not normalized_schema_name:
            return None
        for schema in schemas:
            if schema.name.strip().lower() == normalized_schema_name:
                return schema
        return None

    @staticmethod
    def effective_extraction_value_for_field(
        effective_data: dict[str, Any] | None,
        field_name: str,
    ) -> Any | None:
        """Return one effective extraction field value."""
        if isinstance(effective_data, dict):
            return effective_data.get(field_name)

        return None

    @staticmethod
    def stringify_extraction_facet_value(value: Any) -> str:
        """Serialize one extraction facet value for grouping and display."""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, dict)):
            return json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        return str(value).strip()

    @staticmethod
    def has_meaningful_extraction_value(value: Any) -> bool:
        """Return whether one extraction value should count toward facets."""
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return True

    @classmethod
    def document_class_facets(
        cls,
        facet_rows: list[tuple[str | None, int]],
    ) -> list[DocumentClassFacet]:
        """Convert raw document-class facet rows into response models."""
        return [
            DocumentClassFacet(label=label, count=count)
            for label, count in facet_rows
            if isinstance(label, str) and label
        ]

    @classmethod
    def extraction_schema_facets(
        cls,
        facet_rows: list[tuple[str | None, int]],
    ) -> list[ExtractionSchemaFacet]:
        """Convert raw extraction-schema facet rows into response models."""
        return [
            ExtractionSchemaFacet(schema_name=schema, count=count)
            for schema, count in facet_rows
            if isinstance(schema, str) and schema
        ]
