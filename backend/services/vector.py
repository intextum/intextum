"""Vector service for interacting with pgvector."""

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.vector import VectorChunkUpsert, VectorDocumentChunk, VectorSearchHit
from models.sqlalchemy_models import (
    ContentChunk,
    ContentItemEmailMessageDetails,
    ContentItemEnrichmentState,
    IndexedContentItem,
)
from services.content.invariants import safe_content_item_kind
from services.vector_dimensions import (
    validate_embedding_vector_length,
    validate_embedding_vectors_length,
)

logger = logging.getLogger(__name__)


class VectorService:
    """Service for handling file chunks and embeddings with pgvector."""

    @staticmethod
    def _normalize_extension(file_extension: str) -> str:
        ext = file_extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        return ext

    @staticmethod
    def _chunk_upsert_payload(
        content_item_id: str, chunk: VectorChunkUpsert
    ) -> dict[str, object]:
        payload = chunk.model_dump()
        payload["content_item_id"] = content_item_id
        return payload

    @staticmethod
    async def _source_metadata_map(
        db: AsyncSession,
        content_item_ids: list[str],
    ) -> dict[str, dict[str, object | None]]:
        """Return email/attachment presentation metadata for the supplied content items."""
        if not content_item_ids:
            return {}

        rows = (
            await db.execute(
                select(
                    IndexedContentItem.content_item_id,
                    IndexedContentItem.container_content_item_id,
                    ContentItemEmailMessageDetails.from_address,
                    ContentItemEmailMessageDetails.sent_at,
                    ContentItemEmailMessageDetails.received_at,
                )
                .outerjoin(
                    ContentItemEmailMessageDetails,
                    ContentItemEmailMessageDetails.content_item_id
                    == IndexedContentItem.content_item_id,
                )
                .where(IndexedContentItem.content_item_id.in_(content_item_ids))
            )
        ).all()

        parent_ids = [
            container_content_item_id
            for _content_item_id, container_content_item_id, _from_address, _sent_at, _received_at in rows
            if isinstance(container_content_item_id, str) and container_content_item_id
        ]
        parent_name_map: dict[str, str | None] = {}
        if parent_ids:
            parent_rows = (
                await db.execute(
                    select(
                        IndexedContentItem.content_item_id,
                        IndexedContentItem.display_name,
                        IndexedContentItem.name,
                        IndexedContentItem.relative_path,
                    ).where(IndexedContentItem.content_item_id.in_(parent_ids))
                )
            ).all()
            parent_name_map = {
                content_item_id: display_name or name or relative_path
                for content_item_id, display_name, name, relative_path in parent_rows
            }

        metadata_map: dict[str, dict[str, object | None]] = {}
        for (
            content_item_id,
            container_content_item_id,
            from_address,
            sent_at,
            received_at,
        ) in rows:
            metadata_map[str(content_item_id)] = {
                "email_from_address": from_address
                if isinstance(from_address, str)
                else None,
                "email_sent_at": sent_at or received_at,
                "parent_display_name": (
                    parent_name_map.get(container_content_item_id)
                    if isinstance(container_content_item_id, str)
                    else None
                ),
            }
        return metadata_map

    @staticmethod
    def _search_row_to_result(
        chunk: ContentChunk,
        file: IndexedContentItem,
        score: float,
        *,
        source_metadata: dict[str, object | None] | None = None,
    ) -> VectorSearchHit:
        source_metadata = source_metadata or {}
        return VectorSearchHit(
            score=score,
            file_path=file.relative_path,
            folder_uuid=file.folder_uuid,
            content_item_id=file.content_item_id,
            display_name=file.display_name or file.name or file.relative_path,
            content_kind=safe_content_item_kind(file.content_kind).value,
            email_from_address=(
                source_metadata.get("email_from_address")
                if isinstance(source_metadata.get("email_from_address"), str)
                else None
            ),
            email_sent_at=source_metadata.get("email_sent_at"),
            parent_display_name=(
                source_metadata.get("parent_display_name")
                if isinstance(source_metadata.get("parent_display_name"), str)
                else None
            ),
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            page_numbers=chunk.page_numbers or [],
            headings=chunk.headings or [],
            images=chunk.images or [],
            doc_refs=chunk.doc_refs or [],
        )

    @staticmethod
    def _document_chunk_to_result(
        chunk: ContentChunk,
        file: IndexedContentItem,
        *,
        source_metadata: dict[str, object | None] | None = None,
    ) -> VectorDocumentChunk:
        source_metadata = source_metadata or {}
        return VectorDocumentChunk(
            file_path=file.relative_path,
            content_item_id=file.content_item_id,
            display_name=file.display_name or file.name or file.relative_path,
            content_kind=safe_content_item_kind(file.content_kind).value,
            email_from_address=(
                source_metadata.get("email_from_address")
                if isinstance(source_metadata.get("email_from_address"), str)
                else None
            ),
            email_sent_at=source_metadata.get("email_sent_at"),
            parent_display_name=(
                source_metadata.get("parent_display_name")
                if isinstance(source_metadata.get("parent_display_name"), str)
                else None
            ),
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            page_numbers=chunk.page_numbers or [],
            headings=chunk.headings or [],
            images=chunk.images or [],
            doc_refs=chunk.doc_refs or [],
        )

    @staticmethod
    def _base_semantic_search_stmt(query_vector: list[float]):
        distance_expr = ContentChunk.embedding.cosine_distance(query_vector)
        similarity_expr = 1 - distance_expr
        stmt = select(ContentChunk, IndexedContentItem).join(
            IndexedContentItem,
            ContentChunk.content_item_id == IndexedContentItem.content_item_id,
        )
        return stmt, similarity_expr, distance_expr

    @staticmethod
    def _apply_semantic_search_filters(
        stmt: Any,
        *,
        file_ids: list[str] | None,
        content_kind: str | None,
        file_extension: str | None,
        folder_uuid: str | None,
        path_prefix: str | None,
    ) -> Any:
        if file_ids is not None:
            stmt = stmt.where(ContentChunk.content_item_id.in_(file_ids))

        if content_kind:
            stmt = stmt.where(IndexedContentItem.content_kind == content_kind)
        if file_extension:
            stmt = stmt.where(
                IndexedContentItem.extension
                == VectorService._normalize_extension(file_extension)
            )
        if folder_uuid:
            stmt = stmt.where(IndexedContentItem.folder_uuid == folder_uuid)
        if path_prefix:
            stmt = stmt.where(IndexedContentItem.relative_path.startswith(path_prefix))
        stmt = stmt.outerjoin(
            ContentItemEnrichmentState,
            ContentItemEnrichmentState.content_item_id
            == IndexedContentItem.content_item_id,
        ).where(
            ContentItemEnrichmentState.classification_review_status.is_distinct_from(
                "dismissed"
            )
        )
        return stmt

    @staticmethod
    async def upsert_chunks(
        db: AsyncSession, content_item_id: str, chunks_data: list[VectorChunkUpsert]
    ) -> None:
        """Insert a batch of text chunks and their embeddings into the database.

        This assumes chunks belong to the same index_version.
        """
        if not chunks_data:
            return
        settings = get_settings()
        validate_embedding_vectors_length(
            [chunk.embedding for chunk in chunks_data],
            settings,
            context="chunk.embedding",
        )

        from sqlalchemy.dialects.postgresql import insert

        values = [
            VectorService._chunk_upsert_payload(content_item_id, chunk)
            for chunk in chunks_data
        ]

        stmt = insert(ContentChunk).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "content_item_id": stmt.excluded.content_item_id,
                "text": stmt.excluded.text,
                "embedding": stmt.excluded.embedding,
                "chunk_index": stmt.excluded.chunk_index,
                "page_numbers": stmt.excluded.page_numbers,
                "headings": stmt.excluded.headings,
                "images": stmt.excluded.images,
                "doc_refs": stmt.excluded.doc_refs,
                "index_version": stmt.excluded.index_version,
            },
        )

        await db.execute(stmt)
        await db.commit()
        logger.info("Upserted %d chunks for file %s", len(values), content_item_id)

    @staticmethod
    async def delete_chunks(
        db: AsyncSession, content_item_id: str, exclude_version: str | None = None
    ) -> int:
        """Delete chunks for a file, optionally excluding a specific index_version."""
        stmt = delete(ContentChunk).where(
            ContentChunk.content_item_id == content_item_id
        )
        if exclude_version:
            stmt = stmt.where(ContentChunk.index_version != exclude_version)

        result = await db.execute(stmt)
        await db.commit()
        logger.info("Deleted %d chunks for file %s", result.rowcount, content_item_id)
        return int(result.rowcount or 0)

    @staticmethod
    async def semantic_search(
        db: AsyncSession,
        query_vector: list[float],
        limit: int,
        content_kind: str | None = None,
        file_extension: str | None = None,
        path_prefix: str | None = None,
        folder_uuid: str | None = None,
        score_threshold: float | None = None,
        file_ids: list[str] | None = None,
    ) -> list[VectorSearchHit]:
        """Perform a semantic search using cosine distance (<=>)."""
        settings = get_settings()
        validate_embedding_vector_length(
            query_vector,
            settings,
            context="query_vector",
        )
        stmt, similarity_expr, distance_expr = VectorService._base_semantic_search_stmt(
            query_vector
        )
        stmt = VectorService._apply_semantic_search_filters(
            stmt,
            file_ids=file_ids,
            content_kind=content_kind,
            file_extension=file_extension,
            folder_uuid=folder_uuid,
            path_prefix=path_prefix,
        )
        stmt = stmt.add_columns(similarity_expr.label("similarity"))

        if score_threshold is not None:
            stmt = stmt.where(similarity_expr >= score_threshold)

        stmt = stmt.order_by(distance_expr)
        stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        rows = result.all()
        metadata_map = await VectorService._source_metadata_map(
            db,
            [file.content_item_id for chunk, file, score in rows],
        )
        return [
            VectorService._search_row_to_result(
                chunk,
                file,
                score,
                source_metadata=metadata_map.get(file.content_item_id),
            )
            for chunk, file, score in rows
        ]

    @staticmethod
    async def fetch_document_chunks(
        db: AsyncSession,
        content_item_id: str,
        limit: int = 200,
    ) -> list[VectorDocumentChunk]:
        """Retrieve chunks for a specific document."""
        settings = get_settings()
        limit = min(limit, settings.MAX_VECTOR_CHUNK_LIMIT)

        stmt = (
            select(ContentChunk, IndexedContentItem)
            .join(
                IndexedContentItem,
                ContentChunk.content_item_id == IndexedContentItem.content_item_id,
            )
            .where(ContentChunk.content_item_id == content_item_id)
        )

        stmt = stmt.order_by(ContentChunk.chunk_index)
        stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        rows = result.all()
        metadata_map = await VectorService._source_metadata_map(
            db,
            [file.content_item_id for chunk, file in rows],
        )
        return [
            VectorService._document_chunk_to_result(
                chunk,
                file,
                source_metadata=metadata_map.get(file.content_item_id),
            )
            for chunk, file in rows
        ]
