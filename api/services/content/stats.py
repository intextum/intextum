"""File statistics and search service — flat queries across all sources."""

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import get_settings
from models.enums import ProcessingStatus
from models.content.items import (
    ContentItemKind,
    ContentItemInfo,
    FlatContentItemListResponse,
    ReviewReasonFacet,
    ReviewQueueSummary,
)
from models.sqlalchemy_models import (
    ContentItemAttachmentDetails,
    ContentItemEnrichmentState,
    IndexedContentItem,
)
from models.user import User
from services.ai_settings import (
    AiSettingsService,
    document_classification_config_fingerprint,
    document_extraction_config_fingerprint,
)
from services.utils import find_folder_by_uuid
from .helpers import record_to_file_info, record_to_relation_summary
from ._stats.enrichment import EnrichmentStalenessExpressions
from ._stats.extraction_facets import ExtractionFacetHelpers
from ._stats.filters import (
    FieldPredicate,
    FlatContentListFilters,
    apply_flat_filters,
    apply_flat_sort,
    scope_filters_to_path,
)
from ._stats.global_stats import GlobalContentStatsCollector
from ._stats.listing import FlatContentListingAssembler
from ._stats.paths import FlatContentPathNavigator
from ._stats.query_context import FlatContentQueryContextBuilder
from ._stats.review import ReviewQueryHelpers


class ContentStatsService:
    """Service for file statistics, search, and flat listing queries."""

    REVIEW_REASON_CODES: tuple[str, ...] = (
        "missing_required_fields",
        "conflicted_fields",
        "missing_evidence",
    )

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _flat_file_base_stmt():
        return (
            select(IndexedContentItem)
            .outerjoin(ContentItemEnrichmentState)
            .where(
                IndexedContentItem.is_dir.is_(False),
                IndexedContentItem.is_hidden.is_(False),
            )
        )

    @staticmethod
    def _flat_file_filters(
        *,
        name_contains: str | None = None,
        name_regex: bool = False,
        search_path: bool = False,
        ids: tuple[str, ...] | None = None,
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
    ) -> FlatContentListFilters:
        return FlatContentListFilters(
            name_contains=name_contains,
            name_regex=name_regex,
            search_path=search_path,
            ids=ids,
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
            classification_enabled=classification_enabled,
            extraction_enabled=extraction_enabled,
            classification_fingerprint=classification_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
            extraction_model=extraction_model,
            extraction_schema_models=extraction_schema_models,
        )

    async def _to_file_infos(
        self,
        rows: list[IndexedContentItem],
        *,
        user: User | None = None,
    ) -> list[ContentItemInfo]:
        effective_settings = await AiSettingsService(self.db).get_effective_settings()
        parent_ids = {
            row.parent_content_item_id for row in rows if row.parent_content_item_id
        }
        email_message_ids = {
            row.content_item_id
            for row in rows
            if row.content_kind == ContentItemKind.EMAIL_MESSAGE.value
        }
        parent_records_by_id: dict[str, IndexedContentItem] = {}
        child_records_by_parent_id: dict[str, list[IndexedContentItem]] = defaultdict(
            list
        )

        if parent_ids:
            parent_stmt = select(IndexedContentItem).where(
                IndexedContentItem.content_item_id.in_(parent_ids)
            )
            parent_records = (await self.db.execute(parent_stmt)).scalars().all()
            parent_records_by_id = {
                record.content_item_id: record for record in parent_records
            }

        if email_message_ids:
            child_stmt = (
                select(IndexedContentItem)
                .outerjoin(
                    ContentItemAttachmentDetails,
                    ContentItemAttachmentDetails.content_item_id
                    == IndexedContentItem.content_item_id,
                )
                .where(IndexedContentItem.parent_content_item_id.in_(email_message_ids))
                .order_by(
                    IndexedContentItem.parent_content_item_id,
                    func.coalesce(
                        ContentItemAttachmentDetails.attachment_index, 10_000
                    ),
                    func.lower(
                        func.coalesce(
                            IndexedContentItem.display_name,
                            IndexedContentItem.name,
                            IndexedContentItem.relative_path,
                        )
                    ),
                )
            )
            child_records = (await self.db.execute(child_stmt)).scalars().all()
            for child_record in child_records:
                if child_record.parent_content_item_id:
                    child_records_by_parent_id[
                        child_record.parent_content_item_id
                    ].append(child_record)

        files: list[ContentItemInfo] = []
        for row in rows:
            folder = find_folder_by_uuid(row.folder_uuid)
            if folder:
                file_info = record_to_file_info(
                    row,
                    folder,
                    effective_settings=effective_settings,
                )
                if row.parent_content_item_id:
                    parent_record = parent_records_by_id.get(row.parent_content_item_id)
                    parent_folder = (
                        find_folder_by_uuid(parent_record.folder_uuid)
                        if parent_record is not None
                        else None
                    )
                    if parent_record is not None and parent_folder is not None:
                        file_info.parent_item = record_to_relation_summary(
                            parent_record, parent_folder
                        )
                if row.content_kind == ContentItemKind.EMAIL_MESSAGE.value:
                    file_info.child_items = [
                        record_to_relation_summary(child_record, folder)
                        for child_record in child_records_by_parent_id.get(
                            row.content_item_id, []
                        )
                    ]
                files.append(file_info)
        return files

    async def get_recently_indexed(
        self, user: User | None = None, limit: int = 10
    ) -> list[ContentItemInfo]:
        """Get recently indexed files that the user can access (pure SQL)."""
        stmt = (
            select(IndexedContentItem)
            .where(
                IndexedContentItem.processing_status == ProcessingStatus.COMPLETED,
                IndexedContentItem.is_dir.is_(False),
                IndexedContentItem.processed_at.is_not(None),
            )
            .order_by(desc(IndexedContentItem.processed_at))
        )
        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return await self._to_file_infos(list(result.scalars().all()), user=user)

    async def list_all_files(
        self,
        user: User | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "name",
        sort_order: str = "asc",
        name_contains: str | None = None,
        name_regex: bool = False,
        search_path: bool = False,
        ids: tuple[str, ...] | None = None,
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
    ) -> FlatContentItemListResponse:
        """List files across folders, optionally scoped to one folder subtree."""
        query_context = await FlatContentQueryContextBuilder.build(
            self,
            name_contains=name_contains,
            name_regex=name_regex,
            search_path=search_path,
            ids=ids,
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
        return await FlatContentListingAssembler(
            service=self,
            user=user,
            effective_settings=query_context.effective_settings,
            flat_filters=flat_filters,
            extraction_schema=extraction_schema,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        ).build_response()

    async def list_all_matching_paths(
        self,
        *,
        user: User | None = None,
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
    ) -> list[str]:
        """Return folder-prefixed API paths for all files matching the flat filters."""
        query_context = await FlatContentQueryContextBuilder.build(
            self,
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
        return await FlatContentPathNavigator(
            service=self,
            user=user,
            flat_filters=flat_filters,
            folder_resolver=find_folder_by_uuid,
        ).list_matching_paths()

    @staticmethod
    def _effective_document_class_expr():
        return ExtractionFacetHelpers.effective_document_class_expr()

    @staticmethod
    def _effective_extraction_schema_expr():
        return ExtractionFacetHelpers.effective_extraction_schema_expr()

    @staticmethod
    def _effective_extraction_field_expr(field_name: str):
        return ExtractionFacetHelpers.effective_extraction_field_expr(field_name)

    @classmethod
    def _numeric_extraction_field_expr(cls, field_name: str):
        return ExtractionFacetHelpers.numeric_extraction_field_expr(field_name)

    @classmethod
    def _date_extraction_field_expr(cls, field_name: str):
        return ExtractionFacetHelpers.date_extraction_field_expr(field_name)

    @classmethod
    def _build_document_class_facet_stmt(cls, stmt):
        return ExtractionFacetHelpers.build_document_class_facet_stmt(stmt)

    @classmethod
    def _build_extraction_schema_facet_stmt(cls, stmt):
        return ExtractionFacetHelpers.build_extraction_schema_facet_stmt(stmt)

    @classmethod
    def _build_extraction_field_facet_stmt(
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
    ):
        return ExtractionFacetHelpers.build_extraction_field_facet_stmt(
            user=user,
            filters=filters,
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
            flat_file_filters_builder=cls._flat_file_filters,
            apply_filters=cls._apply_flat_filters,
        )

    @classmethod
    def _build_extraction_schema_field_facet_stmt(
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
    ):
        return ExtractionFacetHelpers.build_extraction_schema_field_facet_stmt(
            user=user,
            filters=filters,
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
            flat_file_filters_builder=cls._flat_file_filters,
            apply_filters=cls._apply_flat_filters,
        )

    @classmethod
    def _build_extraction_value_facet_stmt(
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
    ):
        return ExtractionFacetHelpers.build_extraction_value_facet_stmt(
            user=user,
            filters=filters,
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
            flat_file_filters_builder=cls._flat_file_filters,
            apply_filters=cls._apply_flat_filters,
        )

    @staticmethod
    def _stored_config_fingerprint_expr(column_name: str):
        return EnrichmentStalenessExpressions.stored_config_fingerprint_expr(
            column_name
        )

    @staticmethod
    def _stored_model_expr(column_name: str):
        return EnrichmentStalenessExpressions.stored_model_expr(column_name)

    @staticmethod
    def _review_status_expr(column_name: str):
        return ReviewQueryHelpers.review_status_expr(column_name)

    @classmethod
    def _has_effective_extraction_expr(cls):
        return ReviewQueryHelpers.has_effective_extraction_expr()

    @staticmethod
    def _jsonb_object_key_count_expr(value):
        return ReviewQueryHelpers.jsonb_object_key_count_expr(value)

    @classmethod
    def _unreviewed_enrichment_expr(cls):
        return ReviewQueryHelpers.unreviewed_enrichment_expr()

    @classmethod
    def _accepted_enrichment_expr(cls):
        return ReviewQueryHelpers.accepted_enrichment_expr()

    @classmethod
    def _corrected_enrichment_expr(cls):
        return ReviewQueryHelpers.corrected_enrichment_expr()

    @classmethod
    def _dismissed_enrichment_expr(cls):
        return ReviewQueryHelpers.dismissed_enrichment_expr()

    @classmethod
    def _needs_review_expr(cls):
        return ReviewQueryHelpers.needs_review_expr()

    @classmethod
    def _classification_missing_evidence_expr(cls):
        return ReviewQueryHelpers.classification_missing_evidence_expr()

    @classmethod
    def _extraction_missing_required_expr(cls):
        return ReviewQueryHelpers.extraction_missing_required_expr()

    @classmethod
    def _extraction_conflicted_fields_expr(cls):
        return ReviewQueryHelpers.extraction_conflicted_fields_expr()

    @classmethod
    def _extraction_missing_evidence_expr(cls):
        return ReviewQueryHelpers.extraction_missing_evidence_expr()

    @classmethod
    def _review_reason_expr(cls, review_reason: str):
        return ReviewQueryHelpers.review_reason_expr(review_reason)

    @classmethod
    def _review_priority_expr(cls):
        return ReviewQueryHelpers.review_priority_expr()

    @classmethod
    def _stale_enrichment_expr(
        cls,
        *,
        classification_enabled: bool,
        extraction_enabled: bool,
        classification_fingerprint: str,
        extraction_fingerprint: str,
        extraction_model: str,
        extraction_schema_models: dict[str, str] | None,
    ):
        return EnrichmentStalenessExpressions.stale_enrichment_expr(
            classification_enabled=classification_enabled,
            extraction_enabled=extraction_enabled,
            classification_fingerprint=classification_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
            extraction_model=extraction_model,
            extraction_schema_models=extraction_schema_models,
        )

    @classmethod
    def _collect_extraction_field_facets(
        cls,
        rows: list[tuple[dict[str, Any] | None]],
        limit: int = 8,
    ):
        return ExtractionFacetHelpers.collect_extraction_field_facets(rows, limit=limit)

    @classmethod
    def _collect_extraction_schema_field_facets(
        cls,
        rows: list[tuple[dict[str, Any] | None]],
        *,
        schemas,
    ):
        return ExtractionFacetHelpers.collect_extraction_schema_field_facets(
            rows,
            schemas=schemas,
        )

    @classmethod
    def _collect_extraction_value_facets(
        cls,
        rows: list[tuple[dict[str, Any] | None]],
        *,
        field_name: str,
        limit: int = 8,
    ):
        return ExtractionFacetHelpers.collect_extraction_value_facets(
            rows,
            field_name=field_name,
            limit=limit,
        )

    async def _collect_review_reason_facets(self, stmt) -> list[ReviewReasonFacet]:
        return await ReviewQueryHelpers.collect_review_reason_facets(
            self.db,
            stmt,
            review_reason_codes=self.REVIEW_REASON_CODES,
        )

    async def _collect_review_summary(self, stmt, *, total: int) -> ReviewQueueSummary:
        return await ReviewQueryHelpers.collect_review_summary(
            self.db,
            stmt,
            total=total,
            review_reason_codes=self.REVIEW_REASON_CODES,
        )

    @classmethod
    def _effective_extraction_field_keys(
        cls,
        effective_data: dict[str, Any] | None,
    ) -> list[str]:
        return ExtractionFacetHelpers.effective_extraction_field_keys(
            effective_data,
        )

    @staticmethod
    def _find_configured_extraction_schema(
        schemas,
        raw_schema_name: str | None,
    ):
        return ExtractionFacetHelpers.find_configured_extraction_schema(
            schemas,
            raw_schema_name,
        )

    @staticmethod
    def _effective_extraction_value_for_field(
        effective_data: dict[str, Any] | None,
        field_name: str,
    ) -> Any | None:
        return ExtractionFacetHelpers.effective_extraction_value_for_field(
            effective_data,
            field_name,
        )

    @staticmethod
    def _stringify_extraction_facet_value(value: Any) -> str:
        return ExtractionFacetHelpers.stringify_extraction_facet_value(value)

    @staticmethod
    def _has_meaningful_extraction_value(value: Any) -> bool:
        return ExtractionFacetHelpers.has_meaningful_extraction_value(value)

    @staticmethod
    def _apply_flat_filters(
        stmt,
        filters: FlatContentListFilters | None = None,
        *,
        name_contains: str | None = None,
        name_regex: bool = False,
        search_path: bool = False,
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
    ):
        flat_filters = filters or ContentStatsService._flat_file_filters(
            name_contains=name_contains,
            name_regex=name_regex,
            search_path=search_path,
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
            classification_enabled=classification_enabled,
            extraction_enabled=extraction_enabled,
            classification_fingerprint=classification_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
            extraction_model=extraction_model,
            extraction_schema_models=extraction_schema_models,
        )
        return apply_flat_filters(
            stmt,
            filters=flat_filters,
            expressions=ContentStatsService,
        )

    @staticmethod
    def _apply_flat_sort(stmt, *, sort_by: str, sort_order: str):
        return apply_flat_sort(
            stmt,
            sort_by=sort_by,
            sort_order=sort_order,
            expressions=ContentStatsService,
        )

    async def get_global_stats(self, user: User | None = None) -> dict[str, Any]:
        """Get ACL-filtered statistics for indexed files (excludes directory entries)."""
        effective_settings = await AiSettingsService(self.db).get_effective_settings()
        classification_fingerprint = document_classification_config_fingerprint(
            effective_settings
        )
        extraction_fingerprint = document_extraction_config_fingerprint(
            effective_settings
        )
        return await GlobalContentStatsCollector(
            service=self,
            effective_settings=effective_settings,
            classification_fingerprint=classification_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
        ).collect()
