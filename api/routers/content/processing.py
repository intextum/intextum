"""File processing endpoints."""

import logging
import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Depends, Query
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from database import get_db
from models.enums import ProcessingStatus
from models.content.items import BatchProcessRequest, FilteredBatchProcessRequest
from models.sqlalchemy_models import IndexedContentItem, TaskQueue
from models.user import User
from services.content import ContentService
from services.content.audit import ContentAuditService
from services.content.stats import ContentStatsService
from services.content._stats.filters import parse_field_predicates
from services.task_queue import TaskQueueService
from services.content.helpers import user_can_access_record
from .helpers import (
    get_content_service,
    resolve_authorized_source_file,
    resolve_authorized_source_dir,
    enqueue_single_file,
    get_content_stats_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)

ACTIVE_PROCESSING_STATUSES = (
    ProcessingStatus.QUEUED,
    ProcessingStatus.PROCESSING,
    ProcessingStatus.RETRYING,
)
MISSING_TASK_ABORT_MESSAGE = "Task record missing — aborted manually"


async def _collect_file_paths(adapter, prefix: str) -> list[str]:
    entries = await adapter.list_directory(prefix)
    file_paths: list[str] = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_file:
            file_paths.append(entry.relative_path)
            continue
        if entry.is_dir:
            file_paths.extend(await _collect_file_paths(adapter, entry.relative_path))
    return file_paths


async def _enqueue_relative_path(
    folder,
    relative_path: str,
    db: AsyncSession,
    processing_config: dict[str, object] | None = None,
    requested_by_sub: str | None = None,
) -> tuple[dict | None, int]:
    try:
        result = await enqueue_single_file(
            folder,
            relative_path,
            db,
            processing_config=processing_config,
            requested_by_sub=requested_by_sub,
        )
    except Exception:
        logger.exception("Failed to enqueue content processing for %s", relative_path)
        return None, 1
    if "error" in result:
        return None, 1
    return result, 0


async def _enqueue_paths_in_directory(
    folder,
    dir_rel: str,
    db: AsyncSession,
    processing_config: dict[str, object] | None = None,
    requested_by_sub: str | None = None,
) -> tuple[list[dict], int]:
    adapter = folder.get_adapter()
    tasks: list[dict] = []
    errors = 0
    for rel_path in sorted(await _collect_file_paths(adapter, dir_rel)):
        result, error_count = await _enqueue_relative_path(
            folder,
            rel_path,
            db,
            processing_config=processing_config,
            requested_by_sub=requested_by_sub,
        )
        if result:
            tasks.append(result)
        errors += error_count
    return tasks, errors


async def _enqueue_explicit_paths(
    paths: list[str],
    user: User,
    file_service: ContentService,
    db: AsyncSession,
    processing_config: dict[str, object] | None = None,
    requested_by_sub: str | None = None,
) -> tuple[list[dict], int]:
    tasks: list[dict] = []
    errors = 0
    for path_str in paths:
        try:
            folder, rel_path = await resolve_authorized_source_file(
                path_str, user, file_service
            )
        except HTTPException:
            errors += 1
            continue
        result, error_count = await _enqueue_relative_path(
            folder,
            rel_path,
            db,
            processing_config=processing_config,
            requested_by_sub=requested_by_sub,
        )
        if result:
            tasks.append(result)
        errors += error_count
    return tasks, errors


def _batch_process_response(
    tasks: list[dict],
    errors: int,
    *,
    matched: int | None = None,
) -> dict[str, Any]:
    response = {
        "message": f"Queued {len(tasks)} file(s) for processing",
        "queued": len(tasks),
        "errors": errors,
        "tasks": tasks,
    }
    if matched is not None:
        response["matched"] = matched
    return response


def _validate_content_name_regex(name: str | None, name_regex: bool) -> None:
    if not name or not name_regex:
        return
    try:
        re.compile(name)
    except re.error as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid name regex: {exc}"
        ) from exc


def _ok_response(**values: str) -> dict[str, str]:
    return {"status": "ok", **values}


async def _get_indexed_content_item(
    db: AsyncSession, content_item_id: str
) -> IndexedContentItem | None:
    result = await db.execute(
        select(IndexedContentItem).where(
            IndexedContentItem.content_item_id == content_item_id
        )
    )
    return result.scalar_one_or_none()


async def _get_task(db: AsyncSession, task_id: str) -> TaskQueue | None:
    result = await db.execute(select(TaskQueue).where(TaskQueue.id == task_id))
    return result.scalar_one_or_none()


def _mark_missing_task_aborted(record: IndexedContentItem) -> None:
    record.processing_status = ProcessingStatus.REVOKED
    record.error_message = MISSING_TASK_ABORT_MESSAGE
    record.task_id = None
    record.task_secret = None


@router.post("/process")
async def trigger_process(
    path: str = Query(..., description="File path to process"),
    processing_config: dict[str, Any] | None = Body(default=None, embed=True),
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Trigger processing for a specific file."""
    folder, rel_path = await resolve_authorized_source_file(path, user, file_service)
    user_sub = user.require_stable_sub()

    result = await enqueue_single_file(
        folder,
        rel_path,
        db,
        processing_config=processing_config,
        requested_by_sub=user_sub,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "message": "Processing triggered",
        "task_id": result["task_id"],
        "file_path": path,
    }


@router.post("/process-batch")
async def trigger_batch_process(
    request: BatchProcessRequest,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Trigger processing for multiple files."""
    if bool(request.directory_path) == bool(request.paths):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of directory_path or paths",
        )

    if request.directory_path:
        folder, dir_rel = await resolve_authorized_source_dir(
            request.directory_path, user, file_service
        )
        tasks, errors = await _enqueue_paths_in_directory(
            folder,
            dir_rel,
            db,
            processing_config=request.processing_config,
            requested_by_sub=user.require_stable_sub(),
        )
    else:
        paths = request.paths
        if paths is None:
            raise HTTPException(
                status_code=400,
                detail="Provide exactly one of directory_path or paths",
            )
        tasks, errors = await _enqueue_explicit_paths(
            paths,
            user,
            file_service,
            db,
            processing_config=request.processing_config,
            requested_by_sub=user.require_stable_sub(),
        )

    return _batch_process_response(tasks, errors)


@router.post("/process-batch-filtered")
async def trigger_filtered_batch_process(
    request: FilteredBatchProcessRequest,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    stats_service: ContentStatsService = Depends(get_content_stats_service),
    db: AsyncSession = Depends(get_db),
):
    """Trigger processing for all files that match the current flat-list filters."""
    _validate_content_name_regex(request.name, request.name_regex)
    paths = await stats_service.list_all_matching_paths(
        user=user,
        name_contains=request.name,
        name_regex=request.name_regex,
        search_path=request.search_path,
        path=request.path,
        content_kind=request.content_kind.value if request.content_kind else None,
        extension=request.extension,
        status=request.status,
        document_class=request.document_class,
        extraction_schema=request.extraction_schema,
        extraction_field=request.extraction_field,
        extraction_value=request.extraction_value,
        extraction_value_number_min=request.extraction_value_number_min,
        extraction_value_number_max=request.extraction_value_number_max,
        extraction_value_date_from=request.extraction_value_date_from,
        extraction_value_date_to=request.extraction_value_date_to,
        field_predicates=parse_field_predicates(request.field_filters),
        review_status=request.review_status,
        review_reason=request.review_reason,
        needs_review=request.needs_review,
        stale_enrichment=request.stale_enrichment,
    )
    tasks, errors = await _enqueue_explicit_paths(
        paths,
        user,
        file_service,
        db,
        processing_config=request.processing_config,
        requested_by_sub=user.require_stable_sub(),
    )

    return _batch_process_response(tasks, errors, matched=len(paths))


@router.post("/abort/{content_item_id}")
async def abort_processing(
    content_item_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually abort an active processing task for a file."""
    record = await _get_indexed_content_item(db, content_item_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    if not user_can_access_record(record, user):
        raise HTTPException(status_code=403, detail="Access denied")

    if record.processing_status not in ACTIVE_PROCESSING_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"File is not being processed (status: {record.processing_status})",
        )

    if not record.task_id:
        raise HTTPException(
            status_code=400, detail="No active task ID found for this file"
        )

    task = await _get_task(db, record.task_id)

    if not task:
        _mark_missing_task_aborted(record)
        await ContentAuditService(db).append_for_record(
            record,
            event_type="content.processing.aborted",
            event_group="processing",
            status=ProcessingStatus.REVOKED.value,
            summary="Processing was aborted because the task record was missing",
            metadata={"reason": record.error_message},
            user=user,
            source="ui",
        )
        await db.commit()
        return _ok_response(message="File status reset (task missing)")

    svc = TaskQueueService(db)
    ok = await svc.abort_task(
        task.id,
        task.task_secret,
        reason="Aborted manually via UI",
        actor_sub=user.require_stable_sub(),
        actor_name=user.display_name,
        source="ui",
    )

    if not ok:
        raise HTTPException(status_code=500, detail="Failed to abort task")

    return _ok_response()
