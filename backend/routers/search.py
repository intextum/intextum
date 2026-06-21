"""Search router for semantic document search."""

import logging
from pathlib import PurePosixPath
from typing import Any, NoReturn, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from models.search import SearchRequest, SearchResult, SearchResponse
from models.content.items import ContentItemKind
from models.user import User
from auth.dependencies import require_user
from clients import get_async_embedding_client
from config import get_settings
from database import get_db
from models.sqlalchemy_models import IndexedContentItem
from services.connector import ConnectorRuntimeService
from services.ai_limits import create_embedding_response
from services.content.invariants import safe_content_item_kind
from services.vector import VectorService
from services.vector_dimensions import VectorDimensionMismatchError

router = APIRouter()
logger = logging.getLogger(__name__)
OVERFETCH_MULTIPLIER = 5
MIN_OVERFETCH = 50
MAX_OVERFETCH = 1000


def _search_backend_unavailable(
    exc: Exception, *, log_message: str, detail: str
) -> NoReturn:
    logger.exception(log_message)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
    ) from exc


def _normalize_path_prefix(path_prefix: Optional[str]) -> Optional[str]:
    """Normalize path prefix for consistent matching."""
    if not path_prefix:
        return None
    normalized = str(PurePosixPath(path_prefix.strip().strip("/")))
    return None if normalized in ("", ".") else normalized


def _matches_path_prefix(
    api_path: str, relative_path: str, path_prefix: Optional[str]
) -> bool:
    """Apply strict prefix matching against API path and raw relative path."""
    if not path_prefix:
        return True
    normalized_api_path = str(PurePosixPath(api_path.strip("/")))
    normalized_relative_path = str(PurePosixPath(relative_path.strip("/")))
    return normalized_api_path.startswith(
        path_prefix
    ) or normalized_relative_path.startswith(path_prefix)


def _derive_vector_path_filters(
    path_prefix: Optional[str], folder_name_to_uuid: dict[str, str]
) -> tuple[Optional[str], Optional[str]]:
    """Derive DB-level folder/path filters from an API path prefix."""
    if not path_prefix:
        return None, None

    first_segment, has_slash, remainder = path_prefix.partition("/")
    folder_uuid = folder_name_to_uuid.get(first_segment)
    if folder_uuid:
        return folder_uuid, remainder if has_slash else None

    return None, path_prefix


async def _enrich_search_results(
    db: AsyncSession, results: list[SearchResult]
) -> list[SearchResult]:
    """Attach content-kind-specific metadata for result presentation."""
    content_item_ids = [
        result.content_item_id
        for result in results
        if isinstance(result.content_item_id, str) and result.content_item_id
    ]
    if not content_item_ids:
        return results

    record_stmt = (
        select(IndexedContentItem)
        .options(
            selectinload(IndexedContentItem.email_message_details),
            selectinload(IndexedContentItem.attachment_details),
        )
        .where(IndexedContentItem.content_item_id.in_(content_item_ids))
    )
    records = (await db.execute(record_stmt)).scalars().all()
    records_by_id = {record.content_item_id: record for record in records}

    parent_ids = {
        record.parent_content_item_id
        for record in records
        if isinstance(record.parent_content_item_id, str)
        and record.parent_content_item_id
    }
    parent_records_by_id: dict[str, IndexedContentItem] = {}
    if parent_ids:
        parent_stmt = select(IndexedContentItem).where(
            IndexedContentItem.content_item_id.in_(parent_ids)
        )
        parent_records = (await db.execute(parent_stmt)).scalars().all()
        parent_records_by_id = {
            parent_record.content_item_id: parent_record
            for parent_record in parent_records
        }

    for result in results:
        if not isinstance(result.content_item_id, str) or not result.content_item_id:
            continue
        record = records_by_id.get(result.content_item_id)
        if record is None:
            continue

        result.display_name = record.display_name or record.name or result.display_name
        result.content_kind = safe_content_item_kind(record.content_kind)

        if record.email_message_details is not None:
            result.email_from_address = record.email_message_details.from_address
            result.email_sent_at = (
                record.email_message_details.sent_at
                or record.email_message_details.received_at
            )

        if record.parent_content_item_id:
            parent_record = parent_records_by_id.get(record.parent_content_item_id)
            if parent_record is not None:
                result.parent_display_name = (
                    parent_record.display_name or parent_record.name or None
                )

    return results


def _search_result_from_chunk(chunk: Any, *, api_path: str) -> SearchResult:
    return SearchResult(
        score=chunk.score,
        file_path=api_path,
        content_item_id=chunk.content_item_id,
        display_name=chunk.display_name,
        content_kind=safe_content_item_kind(chunk.content_kind),
        text=chunk.text,
        chunk_index=chunk.chunk_index,
        page_numbers=chunk.page_numbers,
        headings=chunk.headings,
        images=chunk.images,
        doc_refs=chunk.doc_refs,
        payload={
            "content_item_id": chunk.content_item_id,
            "display_name": chunk.display_name,
            "content_kind": chunk.content_kind,
        },
    )


def _best_file_results(
    chunks: list[Any],
    *,
    folder_name_map: dict[str, str],
    path_prefix: str | None,
) -> list[SearchResult]:
    best_by_file: dict[str, SearchResult] = {}
    ordered_file_paths: list[str] = []

    for chunk in chunks:
        relative_path = chunk.file_path
        folder_uuid = chunk.folder_uuid

        # Construct the folder-name-prefixed path expected by /api/content/details/
        folder_name = folder_name_map.get(folder_uuid)
        if not folder_name or not relative_path:
            continue
        api_path = f"{folder_name}/{relative_path}"

        if not _matches_path_prefix(api_path, relative_path, path_prefix):
            continue

        result_item = _search_result_from_chunk(chunk, api_path=api_path)
        previous = best_by_file.get(api_path)
        if previous is None:
            ordered_file_paths.append(api_path)
            best_by_file[api_path] = result_item
        elif result_item.score > previous.score:
            best_by_file[api_path] = result_item

    return [best_by_file[path] for path in ordered_file_paths]


@router.get("/", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=10, ge=1, le=100, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Results offset"),
    content_kind: ContentItemKind | None = Query(
        default=None, description="Filter by content kind"
    ),
    extension: Optional[str] = Query(default=None, description="Filter by file type"),
    path_prefix: Optional[str] = Query(
        default=None, description="Filter by path prefix"
    ),
    score_threshold: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score to include",
    ),
    _user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Search documents using semantic similarity.

    Embeds the query and searches the vector database for similar content.
    """
    return await _execute_search(
        db=db,
        q=q,
        limit=limit,
        offset=offset,
        content_kind=content_kind.value if content_kind else None,
        extension=extension,
        path_prefix=path_prefix,
        score_threshold=score_threshold,
    )


@router.post("/", response_model=SearchResponse)
async def search_post(
    request: SearchRequest,
    _user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Search documents using POST body.

    Alternative to GET for complex queries.
    """
    return await _execute_search(
        db=db,
        q=request.query,
        limit=request.limit,
        offset=request.offset,
        content_kind=request.content_kind.value if request.content_kind else None,
        extension=request.extension,
        path_prefix=request.path_prefix,
        score_threshold=request.score_threshold,
    )


async def _execute_search(
    db: AsyncSession,
    q: str,
    limit: int,
    offset: int,
    content_kind: str | None,
    extension: Optional[str],
    path_prefix: Optional[str],
    score_threshold: Optional[float],
) -> SearchResponse:
    """Shared search implementation for GET and POST handlers."""
    settings = get_settings()
    embed_client = get_async_embedding_client()
    folder_name_to_uuid, folder_name_map = (
        ConnectorRuntimeService().connector_name_maps(browsable_only=True)
    )

    try:
        response = await create_embedding_response(
            embed_client,
            settings,
            model=settings.EMBEDDING_MODEL,
            texts=[q],
        )
        query_vector = response.data[0].embedding
    except HTTPException:
        raise
    except Exception as exc:
        _search_backend_unavailable(
            exc,
            log_message="Embedding request failed",
            detail="Embedding service unavailable",
        )

    normalized_prefix = _normalize_path_prefix(path_prefix)
    folder_uuid_filter, relative_prefix_filter = _derive_vector_path_filters(
        normalized_prefix, folder_name_to_uuid
    )
    candidate_limit = min(
        max((offset + limit) * OVERFETCH_MULTIPLIER, MIN_OVERFETCH),
        MAX_OVERFETCH,
    )

    try:
        results = await VectorService.semantic_search(
            db=db,
            query_vector=query_vector,
            limit=candidate_limit,
            content_kind=content_kind,
            file_extension=extension,
            path_prefix=relative_prefix_filter,
            folder_uuid=folder_uuid_filter,
            score_threshold=score_threshold,
        )
    except VectorDimensionMismatchError as exc:
        _search_backend_unavailable(
            exc,
            log_message="Embedding vector dimension mismatch",
            detail="Embedding vector dimension mismatch",
        )
    except Exception as exc:
        _search_backend_unavailable(
            exc,
            log_message="Postgres vector query failed",
            detail="Search backend unavailable",
        )

    deduped_results = _best_file_results(
        results,
        folder_name_map=folder_name_map,
        path_prefix=normalized_prefix,
    )
    paged_results = deduped_results[offset : offset + limit]
    paged_results = await _enrich_search_results(db, paged_results)
    total = len(deduped_results)
    has_more = (offset + limit) < total or len(results) >= candidate_limit

    return SearchResponse(
        query=q,
        results=paged_results,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )
