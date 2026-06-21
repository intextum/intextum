"""Global aggregate helpers for file stats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import ProcessingStatus
from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem
from services.ai_settings import expected_document_extraction_models_by_schema


class GlobalContentStatsServiceProtocol(Protocol):
    """Internal ContentStatsService surface used by global stat collectors."""

    db: AsyncSession

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
    ): ...


@dataclass(slots=True)
class GlobalContentStatsCollector:
    """Collect global aggregate counts for indexed files."""

    service: GlobalContentStatsServiceProtocol
    effective_settings: Any
    classification_fingerprint: str
    extraction_fingerprint: str

    async def collect(self) -> dict[str, int]:
        """Collect total, processing, and stale-enrichment counts."""
        total_items, total_size_bytes = await self._collect_totals()
        processing_count = await self._collect_processing_count()
        stale_enrichment_count = await self._collect_stale_enrichment_count()
        return {
            "total_items": total_items,
            "total_size_bytes": total_size_bytes,
            "processing_count": processing_count,
            "stale_enrichment_count": stale_enrichment_count,
        }

    async def _collect_totals(self) -> tuple[int, int]:
        stmt = select(
            func.count(IndexedContentItem.content_item_id),
            func.coalesce(func.sum(IndexedContentItem.size_bytes), 0),
        ).where(IndexedContentItem.is_dir.is_(False))
        result = await self.service.db.execute(stmt)
        row = result.fetchone()
        count, total_size = row if row else (0, 0)
        return count or 0, int(total_size) if total_size else 0

    async def _collect_processing_count(self) -> int:
        stmt = (
            select(func.count(IndexedContentItem.content_item_id))
            .outerjoin(ContentItemEnrichmentState)
            .where(
                IndexedContentItem.processing_status.in_(
                    [
                        ProcessingStatus.QUEUED,
                        ProcessingStatus.PROCESSING,
                        ProcessingStatus.RETRYING,
                    ]
                ),
                IndexedContentItem.is_dir.is_(False),
            )
        )
        result = await self.service.db.execute(stmt)
        return result.scalar() or 0

    async def _collect_stale_enrichment_count(self) -> int:
        stmt = (
            select(func.count(IndexedContentItem.content_item_id))
            .outerjoin(ContentItemEnrichmentState)
            .where(
                IndexedContentItem.is_dir.is_(False),
                IndexedContentItem.is_hidden.is_(False),
                self.service._stale_enrichment_expr(
                    classification_enabled=self.effective_settings.document_classification_enabled,
                    extraction_enabled=self.effective_settings.document_extraction_enabled,
                    classification_fingerprint=self.classification_fingerprint,
                    extraction_fingerprint=self.extraction_fingerprint,
                    extraction_model=self.effective_settings.document_extraction_model,
                    extraction_schema_models=expected_document_extraction_models_by_schema(
                        self.effective_settings
                    ),
                ),
            )
        )
        result = await self.service.db.execute(stmt)
        return result.scalar() or 0
