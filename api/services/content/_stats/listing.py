"""Flat file listing assembly helpers for file stats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.content.items import FlatContentItemListResponse
from models.user import User

from .extraction_facets import ExtractionFacetHelpers
from .filters import FlatContentListFilters


class FlatContentStatsServiceProtocol(Protocol):
    """Internal ContentStatsService surface used by the listing assembler."""

    db: AsyncSession
    REVIEW_REASON_CODES: tuple[str, ...]

    @staticmethod
    def _flat_file_base_stmt(): ...

    @staticmethod
    def _apply_flat_filters(stmt, *, filters: FlatContentListFilters): ...

    @staticmethod
    def _apply_flat_sort(stmt, *, sort_by: str, sort_order: str): ...

    @classmethod
    def _build_document_class_facet_stmt(cls, stmt): ...

    @classmethod
    def _build_extraction_schema_facet_stmt(cls, stmt): ...

    @classmethod
    def _build_extraction_schema_field_facet_stmt(cls, *, user, filters): ...

    @classmethod
    def _build_extraction_field_facet_stmt(cls, *, user, filters): ...

    @classmethod
    def _build_extraction_value_facet_stmt(
        cls,
        *,
        user,
        filters,
        extraction_field: str,
    ): ...

    @staticmethod
    def _find_configured_extraction_schema(schemas, raw_schema_name: str | None): ...

    @classmethod
    def _collect_extraction_schema_field_facets(cls, rows, *, schemas): ...

    @classmethod
    def _collect_extraction_field_facets(cls, rows): ...

    @classmethod
    def _collect_extraction_value_facets(cls, rows, *, field_name: str): ...

    async def _collect_review_reason_facets(self, stmt): ...

    async def _collect_review_summary(self, stmt, *, total: int): ...

    async def _to_file_infos(self, rows, *, user=None): ...


@dataclass(slots=True)
class FlatContentListingAssembler:
    """Build one FlatContentItemListResponse from an already-normalized filter state."""

    service: FlatContentStatsServiceProtocol
    user: User | None
    effective_settings: Any
    flat_filters: FlatContentListFilters
    extraction_schema: str | None
    limit: int
    offset: int
    sort_by: str
    sort_order: str

    async def build_response(self) -> FlatContentItemListResponse:
        """Assemble the full flat-file list response with facets and page results."""
        base = self._filtered_base(self.flat_filters)
        total = await self._count_rows(base)
        document_class_facets = await self._document_class_facets()
        extraction_schema_facets = await self._extraction_schema_facets()
        extraction_schema_field_facets = await self._extraction_schema_field_facets()
        extraction_field_facets = await self._extraction_field_facets()
        extraction_value_facets = await self._extraction_value_facets()
        review_reason_facets = await self._review_reason_facets()
        review_summary = await self.service._collect_review_summary(base, total=total)
        files = await self._page_files(base)

        return FlatContentItemListResponse(
            files=files,
            total=total,
            limit=self.limit,
            offset=self.offset,
            has_more=(self.offset + self.limit) < total,
            document_class_facets=document_class_facets,
            extraction_schema_facets=extraction_schema_facets,
            extraction_schema_field_facets=extraction_schema_field_facets,
            extraction_field_facets=extraction_field_facets,
            extraction_value_facets=extraction_value_facets,
            review_reason_facets=review_reason_facets,
            review_summary=review_summary,
        )

    def _filtered_base(self, filters: FlatContentListFilters):
        return self.service._apply_flat_filters(
            self.service._flat_file_base_stmt(),
            filters=filters,
        )

    async def _count_rows(self, stmt) -> int:
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return (await self.service.db.execute(count_stmt)).scalar() or 0

    async def _document_class_facets(self):
        facet_base = self._filtered_base(self.flat_filters.for_document_class_facets())
        facet_rows = (
            await self.service.db.execute(
                self.service._build_document_class_facet_stmt(facet_base)
            )
        ).all()
        return ExtractionFacetHelpers.document_class_facets(facet_rows)

    async def _extraction_schema_facets(self):
        facet_base = self._filtered_base(self.flat_filters.for_schema_facets())
        facet_rows = (
            await self.service.db.execute(
                self.service._build_extraction_schema_facet_stmt(facet_base)
            )
        ).all()
        return ExtractionFacetHelpers.extraction_schema_facets(facet_rows)

    async def _extraction_schema_field_facets(self):
        schemas = self.effective_settings.document_extraction_schemas or []
        if not schemas:
            return []
        # Scope to the selected schema when one is active (with real coverage),
        # otherwise offer the typed union of every configured schema's leaves.
        configured_schema = self.service._find_configured_extraction_schema(
            schemas,
            self.extraction_schema,
        )
        target_schemas = (
            [configured_schema] if configured_schema is not None else list(schemas)
        )
        facet_rows = (
            await self.service.db.execute(
                self.service._build_extraction_schema_field_facet_stmt(
                    user=self.user,
                    filters=self.flat_filters,
                )
            )
        ).all()
        return self.service._collect_extraction_schema_field_facets(
            facet_rows,
            schemas=target_schemas,
        )

    async def _extraction_field_facets(self):
        facet_rows = (
            await self.service.db.execute(
                self.service._build_extraction_field_facet_stmt(
                    user=self.user,
                    filters=self.flat_filters,
                )
            )
        ).all()
        return self.service._collect_extraction_field_facets(facet_rows)

    async def _extraction_value_facets(self):
        field_name = self.flat_filters.normalized_extraction_field
        if not field_name:
            return []
        facet_rows = (
            await self.service.db.execute(
                self.service._build_extraction_value_facet_stmt(
                    user=self.user,
                    filters=self.flat_filters,
                    extraction_field=field_name,
                )
            )
        ).all()
        return self.service._collect_extraction_value_facets(
            facet_rows,
            field_name=field_name,
        )

    async def _review_reason_facets(self):
        review_reason_base = self._filtered_base(
            self.flat_filters.for_review_reason_facets()
        )
        return await self.service._collect_review_reason_facets(review_reason_base)

    async def _page_files(self, base):
        stmt = self.service._apply_flat_sort(
            base,
            sort_by=self.sort_by,
            sort_order=self.sort_order,
        )
        stmt = stmt.offset(self.offset).limit(self.limit)
        rows = (await self.service.db.execute(stmt)).scalars().all()
        return await self.service._to_file_infos(list(rows), user=self.user)
