"""Shared flat-file filter and sort helpers for file stats queries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from sqlalchemy import cast, desc, func, literal, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import UserDefinedType

from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem

NUMERIC_LEAF_DTYPES = frozenset({"int", "float", "currency"})
KNOWN_FIELD_FILTER_OPERATORS = frozenset(
    {
        "contains",
        "not_contains",
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "between",
        "is_true",
        "is_false",
    }
)
_COMPARISON_JSONPATH_OPS = {
    "eq": "==",
    "ne": "==",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


class JSONPATH(UserDefinedType):
    """Minimal ``jsonpath`` column type so we can cast bind params safely."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "JSONPATH"


@dataclass(frozen=True)
class PathSegment:
    """One step of an extracted-data path: an object key or an array wildcard."""

    key: str | None = None
    elem: bool = False


@dataclass(frozen=True)
class FieldPredicate:
    """One extracted-field filter condition over a JSON path: ``path <op> value``."""

    op: str
    segments: tuple[PathSegment, ...] = ()
    value: str = ""
    value2: str = ""
    dtype: str = "str"


def _parse_segments(entry: dict[str, Any]) -> tuple[PathSegment, ...]:
    raw_segments = entry.get("segments")
    if isinstance(raw_segments, list):
        segments: list[PathSegment] = []
        for raw in raw_segments:
            if not isinstance(raw, dict):
                continue
            if raw.get("elem") is True:
                segments.append(PathSegment(elem=True))
                continue
            key = raw.get("k")
            if isinstance(key, str) and key:
                segments.append(PathSegment(key=key))
        if any(segment.key for segment in segments):
            return tuple(segments)
    # Legacy flat predicates carried a single top-level field name.
    field_name = str(entry.get("field", "")).strip()
    return (PathSegment(key=field_name),) if field_name else ()


def parse_field_predicates(raw: str | None) -> tuple[FieldPredicate, ...]:
    """Parse the JSON ``field_filters`` query param into predicates.

    Malformed entries are skipped rather than raising, so a partially invalid
    filter set never takes down the listing endpoint.
    """
    if not raw:
        return ()
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if not isinstance(decoded, list):
        return ()

    predicates: list[FieldPredicate] = []
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        op = str(entry.get("op", "")).strip()
        if op not in KNOWN_FIELD_FILTER_OPERATORS:
            continue
        segments = _parse_segments(entry)
        if not segments:
            continue
        predicates.append(
            FieldPredicate(
                op=op,
                segments=segments,
                value=str(entry.get("value", "")),
                value2=str(entry.get("value2", "")),
                dtype=str(entry.get("dtype", "str")).strip().lower() or "str",
            )
        )
    return tuple(predicates)


def _escape_jsonpath_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _segments_to_jsonpath(segments: tuple[PathSegment, ...]) -> str:
    parts = ["$"]
    for segment in segments:
        if segment.elem:
            parts.append("[*]")
        elif segment.key is not None:
            parts.append(f'."{_escape_jsonpath_string(segment.key)}"')
    return "".join(parts)


def _leaf_kind(dtype: str) -> str:
    if dtype in NUMERIC_LEAF_DTYPES:
        return "number"
    if dtype == "date":
        return "date"
    return "string"


def _coerce_leaf_value(value: str, kind: str) -> float | str | None:
    trimmed = value.strip()
    if not trimmed:
        return None
    if kind == "number":
        try:
            return float(trimmed)
        except ValueError:
            return None
    return trimmed


def _kind_guard(kind: str) -> str | None:
    if kind == "number":
        return '@.type() == "number"'
    if kind in {"date", "string"}:
        return '@.type() == "string"'
    return None


def compile_predicate_jsonpath(
    predicate: FieldPredicate,
) -> tuple[str, dict[str, Any], bool] | None:
    """Compile a predicate into ``(jsonpath, vars, negate)`` or ``None`` to skip."""
    if not predicate.segments:
        return None
    op = predicate.op
    base = _segments_to_jsonpath(predicate.segments)

    if op == "is_true":
        return (f"{base} ? (@ == true)", {}, False)
    if op == "is_false":
        return (f"{base} ? (@ == false)", {}, False)

    kind = _leaf_kind((predicate.dtype or "str").lower())
    guard = _kind_guard(kind)
    value = (predicate.value or "").strip()

    if op in {"contains", "not_contains"}:
        if not value:
            return None
        pattern = _escape_jsonpath_string(re.escape(value))
        filt = f'@.type() == "string" && @ like_regex "{pattern}" flag "i"'
        return (f"{base} ? ({filt})", {}, op == "not_contains")

    if op == "between":
        low = _coerce_leaf_value(value, kind)
        high = _coerce_leaf_value(predicate.value2 or "", kind)
        bounds: list[str] = []
        vars_: dict[str, Any] = {}
        if low is not None:
            bounds.append("@ >= $lo")
            vars_["lo"] = low
        if high is not None:
            bounds.append("@ <= $hi")
            vars_["hi"] = high
        if not bounds:
            return None
        clauses = ([guard] if guard else []) + bounds
        return (f"{base} ? ({' && '.join(clauses)})", vars_, False)

    comparison = _COMPARISON_JSONPATH_OPS.get(op)
    if comparison is None:
        return None
    target = _coerce_leaf_value(value, kind)
    if target is None:
        return None
    clauses = ([guard] if guard else []) + [f"@ {comparison} $v"]
    return (f"{base} ? ({' && '.join(clauses)})", {"v": target}, op == "ne")


def field_predicate_condition(predicate: FieldPredicate):
    """Build the SQL condition for one field predicate, or ``None`` to skip it.

    Each predicate compiles to a single ``jsonb_path_exists`` over the effective
    extraction JSON, so scalars, ``list[]`` elements and ``object_list[].child``
    values share one mechanism with array-existential semantics.
    """
    compiled = compile_predicate_jsonpath(predicate)
    if compiled is None:
        return None
    jsonpath, vars_, negate = compiled
    exists = func.jsonb_path_exists(
        ContentItemEnrichmentState.extraction_effective_data_json,
        cast(literal(jsonpath), JSONPATH()),
        cast(literal(json.dumps(vars_)), JSONB),
        literal(True),
    )
    return ~exists if negate else exists


@dataclass(frozen=True)
class FlatContentListFilters:
    """Normalized flat-file filter inputs reused across file stats queries."""

    name_contains: str | None = None
    name_regex: bool = False
    search_path: bool = False
    # Folder scope: when set, results are limited to one connector subtree.
    path_folder_uuid: str | None = None
    path_relative_prefix: str = ""
    content_kind: str | None = None
    extension: str | None = None
    status: str | None = None
    document_class: str | None = None
    extraction_schema: str | None = None
    extraction_field: str | None = None
    extraction_value: str | None = None
    extraction_value_number_min: float | None = None
    extraction_value_number_max: float | None = None
    extraction_value_date_from: date | None = None
    extraction_value_date_to: date | None = None
    field_predicates: tuple[FieldPredicate, ...] = field(default_factory=tuple)
    review_status: str | None = None
    review_reason: str | None = None
    needs_review: bool = False
    stale_enrichment: bool = False
    classification_enabled: bool = False
    extraction_enabled: bool = False
    classification_fingerprint: str = ""
    extraction_fingerprint: str = ""
    extraction_model: str = ""
    extraction_schema_models: dict[str, str] | None = None

    @property
    def normalized_extraction_field(self) -> str:
        """Return the active extraction field filter without surrounding whitespace."""
        return self.extraction_field.strip() if self.extraction_field else ""

    @property
    def normalized_name_filter(self) -> str:
        """Return the active filename/path search filter without surrounding whitespace."""
        return self.name_contains.strip() if self.name_contains else ""

    @property
    def normalized_extraction_value(self) -> str:
        """Return the active extraction value filter lowercased for ilike matching."""
        return self.extraction_value.strip().lower() if self.extraction_value else ""

    def for_document_class_facets(self) -> FlatContentListFilters:
        """Reuse the current filters while ignoring the active class self-filter."""
        return replace(self, document_class=None, review_reason=None)

    def for_schema_facets(self) -> FlatContentListFilters:
        """Reuse the current filters while ignoring the active schema self-filter."""
        return replace(
            self,
            extraction_schema=None,
            review_reason=None,
        )

    def for_extraction_field_facets(self) -> FlatContentListFilters:
        """Reuse the current filters while ignoring field-name self-filtering."""
        return replace(self, extraction_field=None)

    def for_extraction_schema_field_facets(self) -> FlatContentListFilters:
        """Reuse the current filters while ignoring field-specific filters entirely."""
        return replace(
            self,
            extraction_field=None,
            extraction_value=None,
            extraction_value_number_min=None,
            extraction_value_number_max=None,
            extraction_value_date_from=None,
            extraction_value_date_to=None,
            field_predicates=(),
        )

    def for_extraction_value_facets(self) -> FlatContentListFilters:
        """Reuse the current filters while keeping the focus field but not its conditions."""
        return replace(self, extraction_value=None, field_predicates=())

    def for_review_reason_facets(self) -> FlatContentListFilters:
        """Reuse the current filters while ignoring the active reason self-filter."""
        return replace(self, review_reason=None)


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a literal path prefix matches verbatim."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def scope_filters_to_path(
    filters: FlatContentListFilters, path: str | None
) -> FlatContentListFilters:
    """Limit flat filters to one connector subtree from a folder-prefixed path."""
    if not path or not path.strip():
        return filters
    # Lazy import keeps this leaf module free of content-service import cycles.
    from services.content.helpers import resolve_db_context

    folder, relative_prefix = resolve_db_context(path)
    return replace(
        filters,
        path_folder_uuid=folder.uuid,
        path_relative_prefix=relative_prefix,
    )


def apply_flat_filters(stmt, *, filters: FlatContentListFilters, expressions: Any):
    """Apply the reusable flat-file filter set to a SQLAlchemy statement."""
    if filters.path_folder_uuid:
        stmt = stmt.where(IndexedContentItem.folder_uuid == filters.path_folder_uuid)
        prefix = filters.path_relative_prefix
        if prefix:
            escaped = _escape_like(prefix)
            stmt = stmt.where(
                or_(
                    IndexedContentItem.relative_path == prefix,
                    IndexedContentItem.relative_path.like(f"{escaped}/%", escape="\\"),
                )
            )
    normalized_name = filters.normalized_name_filter
    if normalized_name:
        search_columns = [IndexedContentItem.name]
        if filters.search_path:
            search_columns.append(IndexedContentItem.relative_path)
        if filters.name_regex:
            full_match_pattern = f"^(?:{normalized_name})$"
            stmt = stmt.where(
                or_(*(column.op("~*")(full_match_pattern) for column in search_columns))
            )
        else:
            pattern = f"%{normalized_name}%"
            stmt = stmt.where(
                or_(*(column.ilike(pattern) for column in search_columns))
            )
    if filters.content_kind:
        stmt = stmt.where(IndexedContentItem.content_kind == filters.content_kind)
    if filters.extension:
        ext = filters.extension.lstrip(".")
        stmt = stmt.where(IndexedContentItem.extension == f".{ext}")
    if filters.status:
        stmt = stmt.where(IndexedContentItem.processing_status == filters.status)
    if filters.document_class:
        normalized_class = filters.document_class.strip().lower()
        if normalized_class:
            stmt = stmt.where(
                func.lower(expressions._effective_document_class_expr()).like(
                    f"%{normalized_class}%"
                )
            )
    if filters.extraction_schema:
        normalized_schema = filters.extraction_schema.strip().lower()
        if normalized_schema:
            stmt = stmt.where(
                func.lower(expressions._effective_extraction_schema_expr()).like(
                    f"%{normalized_schema}%"
                )
            )

    for predicate in filters.field_predicates:
        condition = field_predicate_condition(predicate)
        if condition is not None:
            stmt = stmt.where(condition)

    if filters.review_status == "accepted":
        stmt = stmt.where(expressions._accepted_enrichment_expr())
    elif filters.review_status == "corrected":
        stmt = stmt.where(expressions._corrected_enrichment_expr())
    elif filters.review_status == "dismissed":
        stmt = stmt.where(expressions._dismissed_enrichment_expr())
    elif filters.review_status == "unreviewed":
        stmt = stmt.where(expressions._unreviewed_enrichment_expr())

    if filters.review_reason:
        stmt = stmt.where(expressions._review_reason_expr(filters.review_reason))

    if filters.needs_review:
        stmt = stmt.where(expressions._needs_review_expr())

    if filters.stale_enrichment:
        stmt = stmt.where(
            expressions._stale_enrichment_expr(
                classification_enabled=filters.classification_enabled,
                extraction_enabled=filters.extraction_enabled,
                classification_fingerprint=filters.classification_fingerprint,
                extraction_fingerprint=filters.extraction_fingerprint,
                extraction_model=filters.extraction_model,
                extraction_schema_models=filters.extraction_schema_models,
            )
        )
    return stmt


def apply_flat_sort(stmt, *, sort_by: str, sort_order: str, expressions: Any):
    """Apply one of the supported flat-file sort orders to a statement."""
    sort_column_map = {
        "name": func.lower(IndexedContentItem.name),
        "size": IndexedContentItem.size_bytes,
        "modified": IndexedContentItem.modified_time,
        "extension": IndexedContentItem.extension,
        "review_priority": expressions._review_priority_expr(),
    }
    sort_col = sort_column_map.get(sort_by, func.lower(IndexedContentItem.name))
    if sort_by == "review_priority":
        if sort_order == "desc":
            return stmt.order_by(
                desc(sort_col),
                desc(IndexedContentItem.modified_time),
                func.lower(IndexedContentItem.name),
            )
        return stmt.order_by(
            sort_col,
            desc(IndexedContentItem.modified_time),
            func.lower(IndexedContentItem.name),
        )
    if sort_order == "desc":
        return stmt.order_by(desc(sort_col))
    return stmt.order_by(sort_col)
