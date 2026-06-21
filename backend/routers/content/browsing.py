"""File browsing endpoints."""

import logging
import mimetypes
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user, require_admin
from database import get_db
from models.content.items import (
    ContentItemListResponse,
    FlatContentItemListResponse,
    ContentTreeResponse,
    ContentItemInfo,
    ContentItemChunksResponse,
    ChunkInfo,
    ContentItemKind,
)
from models.user import User
from models.vector import VectorDocumentChunk
from services.content import ContentService, ContentStatsService
from services.content._stats.filters import parse_field_predicates
from services.content.enrichment.csv_export import build_extracted_data_csv
from services.connector import ConnectorRuntimeService
from services.vector import VectorService
from services.utils import compute_content_item_id
from .helpers import (
    get_content_service,
    get_content_stats_service,
    run_file_service_operation,
    resolve_authorized_source_file,
    PREVIEW_MIME_TYPES,
    EXTENSION_MIME_MAP,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_content_name_regex(name: str | None, name_regex: bool) -> None:
    if not name or not name_regex:
        return
    try:
        re.compile(name)
    except re.error as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid name regex: {exc}"
        ) from exc


def _guess_media_type(filename: str) -> str:
    media_type, _ = mimetypes.guess_type(filename)
    return media_type or "application/octet-stream"


def _resolve_preview_media_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    media_type = EXTENSION_MIME_MAP.get(ext) or _guess_media_type(filename)
    if media_type not in PREVIEW_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Preview not supported for this file type: {media_type or 'unknown'}",
        )
    return media_type


async def _build_adapter_file_response(
    adapter,
    rel_path: str,
    *,
    media_type: str,
    disposition: str,
    filename: str,
):
    local_path = await adapter.get_local_path(rel_path)
    if local_path:
        return FileResponse(
            path=local_path,
            filename=filename,
            media_type=media_type,
            content_disposition_type=disposition,
        )

    stream = await adapter.read_file(rel_path)
    return StreamingResponse(
        stream,
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _to_chunk_info(chunk: VectorDocumentChunk) -> ChunkInfo:
    text = chunk.text
    return ChunkInfo(
        chunk_index=chunk.chunk_index,
        text=text,
        page_numbers=chunk.page_numbers,
        headings=chunk.headings,
        images=chunk.images,
        doc_refs=chunk.doc_refs,
        word_count=len(text.split()) if text else 0,
        char_count=len(text) if text else 0,
    )


@router.get("/folders")
async def list_folders(
    user: User = Depends(require_admin),
):
    """List all configured data sources (admin only)."""
    _ = user
    return [
        {
            "uuid": f.uuid,
            "name": f.name,
            "watch": getattr(f, "watch", False),
            "auto_process_new": f.auto_process_new,
            "immutable": getattr(f, "immutable", False),
        }
        for f in ConnectorRuntimeService().browsable_connectors()
    ]


@router.get("/all", response_model=FlatContentItemListResponse)
async def list_all_files(
    limit: int = Query(default=50, ge=1, le=200, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    sort_by: str = Query(
        default="name",
        description="Sort column",
        pattern="^(name|size|modified|extension|review_priority)$",
    ),
    sort_order: str = Query(
        default="asc", description="Sort direction", pattern="^(asc|desc)$"
    ),
    name: str = Query(default=None, description="Filter by name (contains)"),
    name_regex: bool = Query(
        default=False,
        description="Interpret the name filter as a case-insensitive regular expression",
    ),
    search_path: bool = Query(
        default=False,
        description="Apply the name filter to relative paths as well as filenames",
    ),
    path: str = Query(
        default=None,
        description="Scope results to one folder subtree (folder-prefixed path)",
    ),
    content_kind: ContentItemKind | None = Query(
        default=None,
        description="Filter by content kind",
    ),
    extension: str = Query(default=None, description="Filter by file extension"),
    status: str = Query(default=None, description="Filter by processing status"),
    document_class: str = Query(
        default=None, description="Filter by effective document class"
    ),
    extraction_schema: str = Query(
        default=None, description="Filter by effective extraction schema"
    ),
    extraction_field: str = Query(
        default=None, description="Filter by extracted field name"
    ),
    extraction_value: str = Query(
        default=None, description="Filter by extracted field value"
    ),
    extraction_value_number_min: float | None = Query(
        default=None,
        description="Numeric minimum for the selected extracted field",
    ),
    extraction_value_number_max: float | None = Query(
        default=None,
        description="Numeric maximum for the selected extracted field",
    ),
    extraction_value_date_from: date | None = Query(
        default=None,
        description="Earliest ISO date for the selected extracted field",
    ),
    extraction_value_date_to: date | None = Query(
        default=None,
        description="Latest ISO date for the selected extracted field",
    ),
    review_status: str = Query(
        default=None,
        description="Filter by enrichment review status",
        pattern="^(accepted|corrected|unreviewed)$",
    ),
    review_reason: str = Query(
        default=None,
        description="Filter by enrichment review reason",
        pattern="^(missing_required_fields|conflicted_fields|missing_evidence)$",
    ),
    needs_review: bool = Query(
        default=False,
        description="Filter to files whose extracted data still needs human review",
    ),
    stale_enrichment: bool = Query(
        default=False,
        description="Filter to files whose enrichment results are stale for current settings",
    ),
    field_filters: str = Query(
        default=None,
        description="JSON array of extracted-field conditions [{field, op, value, value2, dtype}]",
    ),
    user: User = Depends(require_user),
    stats_service: ContentStatsService = Depends(get_content_stats_service),
):
    """List files across folders, optionally scoped to one folder subtree."""
    _validate_content_name_regex(name, name_regex)
    return await run_file_service_operation(
        lambda: stats_service.list_all_files(
            user=user,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            name_contains=name,
            name_regex=name_regex,
            search_path=search_path,
            path=path,
            content_kind=content_kind.value if content_kind else None,
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
            field_predicates=parse_field_predicates(field_filters),
            review_status=review_status,
            review_reason=review_reason,
            needs_review=needs_review,
            stale_enrichment=stale_enrichment,
        )
    )


@router.get("/extracted-data.csv")
async def export_extracted_data_csv(
    name: str = Query(default=None, description="Filter by name (contains)"),
    name_regex: bool = Query(
        default=False,
        description="Interpret the name filter as a case-insensitive regular expression",
    ),
    search_path: bool = Query(
        default=False,
        description="Apply the name filter to relative paths as well as filenames",
    ),
    path: str = Query(
        default=None,
        description="Scope results to one folder subtree (folder-prefixed path)",
    ),
    content_kind: ContentItemKind | None = Query(
        default=None,
        description="Filter by content kind",
    ),
    extension: str = Query(default=None, description="Filter by file extension"),
    status: str = Query(default=None, description="Filter by processing status"),
    document_class: str = Query(
        default=None, description="Filter by effective document class"
    ),
    extraction_schema: str = Query(
        default=None, description="Filter by effective extraction schema"
    ),
    extraction_field: str = Query(
        default=None, description="Filter by extracted field name"
    ),
    extraction_value: str = Query(
        default=None, description="Filter by extracted field value"
    ),
    extraction_value_number_min: float | None = Query(
        default=None,
        description="Numeric minimum for the selected extracted field",
    ),
    extraction_value_number_max: float | None = Query(
        default=None,
        description="Numeric maximum for the selected extracted field",
    ),
    extraction_value_date_from: date | None = Query(
        default=None,
        description="Earliest ISO date for the selected extracted field",
    ),
    extraction_value_date_to: date | None = Query(
        default=None,
        description="Latest ISO date for the selected extracted field",
    ),
    review_status: str = Query(
        default=None,
        description="Filter by enrichment review status",
        pattern="^(accepted|corrected|unreviewed)$",
    ),
    review_reason: str = Query(
        default=None,
        description="Filter by enrichment review reason",
        pattern="^(missing_required_fields|conflicted_fields|missing_evidence)$",
    ),
    needs_review: bool = Query(
        default=False,
        description="Filter to files whose extracted data still needs human review",
    ),
    stale_enrichment: bool = Query(
        default=False,
        description="Filter to files whose enrichment results are stale for current settings",
    ),
    field_filters: str = Query(
        default=None,
        description="JSON array of extracted-field conditions [{field, op, value, value2, dtype}]",
    ),
    user: User = Depends(require_user),
    stats_service: ContentStatsService = Depends(get_content_stats_service),
):
    """Export effective extracted data for all files matching the flat filters."""
    _validate_content_name_regex(name, name_regex)
    csv_content = await build_extracted_data_csv(
        stats_service,
        user=user,
        name_contains=name,
        name_regex=name_regex,
        search_path=search_path,
        path=path,
        content_kind=content_kind.value if content_kind else None,
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
        field_predicates=parse_field_predicates(field_filters),
        review_status=review_status,
        review_reason=review_reason,
        needs_review=needs_review,
        stale_enrichment=stale_enrichment,
    )
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="extracted-data.csv"'},
    )


@router.get("/", response_model=ContentItemListResponse)
async def list_files(
    path: str = Query(default="", description="Directory path relative to root"),
    include_hidden: bool = Query(default=False, description="Include hidden files"),
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
):
    """List files and folders in a directory."""
    return await run_file_service_operation(
        lambda: file_service.list_directory(path, user, include_hidden)
    )


@router.get("/tree", response_model=ContentTreeResponse)
async def get_file_tree(
    path: str = Query(default="", description="Root path for the tree"),
    depth: int = Query(default=1, ge=1, le=5, description="Depth of tree expansion"),
    include_hidden: bool = Query(default=False, description="Include hidden files"),
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
):
    """Get a file tree structure starting from a directory."""
    return await run_file_service_operation(
        lambda: file_service.get_file_tree(path, user, depth, include_hidden)
    )


@router.get("/details/{file_path:path}", response_model=ContentItemInfo)
async def get_file_details(
    file_path: str,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
):
    """Get detailed information about a specific file."""
    return await run_file_service_operation(
        lambda: file_service.get_file_details(file_path, user),
        allow_value_error=True,
    )


@router.get("/item/{content_item_id}", response_model=ContentItemInfo)
async def get_file_details_by_id(
    content_item_id: str,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
):
    """Get detailed information about a specific file by content item id."""
    return await run_file_service_operation(
        lambda: file_service.get_file_details_by_id(content_item_id, user),
        allow_value_error=True,
    )


@router.get("/chunks/{file_path:path}", response_model=ContentItemChunksResponse)
async def get_content_chunks(
    file_path: str,
    limit: int = Query(
        default=100, ge=1, le=1000, description="Maximum chunks to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of chunks to skip"),
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Get vector database chunks for a file."""
    folder, rel_path = await resolve_authorized_source_file(
        file_path, user, file_service
    )
    content_item_id = compute_content_item_id(folder.uuid, rel_path)

    try:
        raw_chunks = await VectorService.fetch_document_chunks(
            db=db,
            content_item_id=content_item_id,
            limit=limit + offset,
        )
    except Exception as exc:
        logger.exception("Vector DB error for %s", file_path)
        raise HTTPException(
            status_code=502, detail="Failed to fetch file chunks"
        ) from exc

    paginated = raw_chunks[offset : offset + limit] if offset < len(raw_chunks) else []
    chunks = [_to_chunk_info(chunk) for chunk in paginated]

    return ContentItemChunksResponse(
        file_path=file_path,
        chunks=chunks,
        total_chunks=len(raw_chunks),
        is_indexed=len(raw_chunks) > 0,
    )


@router.get("/download/{file_path:path}")
async def download_file(
    file_path: str,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
):
    """Download a file."""
    folder, rel_path = await resolve_authorized_source_file(
        file_path, user, file_service
    )
    adapter = folder.get_adapter()
    filename = Path(rel_path).name
    return await _build_adapter_file_response(
        adapter,
        rel_path,
        media_type=_guess_media_type(filename),
        disposition="attachment",
        filename=filename,
    )


@router.get("/preview/{file_path:path}")
async def preview_file(
    file_path: str,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
):
    """Preview a file inline."""
    folder, rel_path = await resolve_authorized_source_file(
        file_path, user, file_service
    )
    adapter = folder.get_adapter()
    filename = Path(rel_path).name
    return await _build_adapter_file_response(
        adapter,
        rel_path,
        media_type=_resolve_preview_media_type(filename),
        disposition="inline",
        filename=filename,
    )
