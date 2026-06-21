"""File mutation endpoints — upload, mkdir, delete."""

from contextlib import suppress
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from config import get_settings
from database import get_db
from models.task_queue import EnqueueProcessTask, ProcessTaskMetadata
from models.user import User
from services.adapters.base import DataConnectorWriteTooLargeError
from services.content import ContentService
from services.content.audit import ContentAuditService
from services.content.deletion import ContentDeletionService
from services.content.indexed_content_item import (
    upsert_indexed_content_item,
    upsert_directory_entry,
)
from services.content.indexing import determine_processing_status
from services.permission import PermissionService
from services.task_queue import TaskQueueService
from services.utils import compute_content_item_id
from .helpers import (
    get_content_service,
    resolve_authorized_source_file,
    resolve_authorized_source_dir,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_UPLOAD_CONTENT_LENGTH_OVERHEAD_BYTES = 1024 * 1024


def _ensure_mutable_source(folder) -> None:
    if getattr(folder, "immutable", False):
        raise HTTPException(status_code=403, detail="Source is immutable")


def _sanitize_filename(filename: str | None) -> str:
    if not filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    safe_name = Path(filename).name
    if not safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe_name


def _child_relative_path(parent_rel: str, name: str) -> str:
    return f"{parent_rel}/{name}" if parent_rel else name


def _ok_response(**values: object) -> dict[str, object]:
    return {"status": "ok", **values}


def _task_metadata(
    entry,
    content_item_id: str,
    *,
    source_name: str | None = None,
) -> ProcessTaskMetadata:
    return ProcessTaskMetadata(
        content_item_id=content_item_id,
        size_bytes=entry.size_bytes,
        modified_time=entry.modified_time,
        created_time=entry.change_time,
        is_symlink=entry.is_symlink,
        file_extension=Path(entry.name).suffix.lower() or None,
        source_name=source_name,
    )


async def _effective_viewers(
    db: AsyncSession, folder_uuid: str
) -> tuple[list[str], list[str]]:
    perm_svc = PermissionService(db)
    return await perm_svc.compute_effective_viewers(folder_uuid)


async def _cleanup_uploaded_file(adapter, relative_path: str) -> None:
    with suppress(Exception):
        await adapter.delete(relative_path)


def _reject_obviously_oversized_content_length(
    request: Request, *, max_bytes: int
) -> None:
    raw_content_length = request.headers.get("content-length")
    if raw_content_length is None:
        return
    try:
        content_length = int(raw_content_length)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid Content-Length header"
        ) from exc
    if content_length < 0:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header")

    # Multipart bodies include boundaries and headers, so leave headroom and let
    # the adapter's streaming limit make the exact file-size decision.
    if content_length > max_bytes + _UPLOAD_CONTENT_LENGTH_OVERHEAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds maximum size of {max_bytes} bytes",
        )


@router.post("/upload")
async def upload_file(
    request: Request,
    directory: str = Query(
        ..., description="Target directory path (folder_name/sub/path)"
    ),
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file into an existing directory.

    The directory path uses the same folder-name-prefixed format as browsing
    endpoints (e.g. ``my-source/subdir``).  The uploaded file is written via
    the source's adapter, so it works for local filesystems and S3 alike.
    """
    folder, dir_rel = await resolve_authorized_source_dir(directory, user, file_service)
    _ensure_mutable_source(folder)
    adapter = folder.get_adapter()

    safe_name = _sanitize_filename(file.filename)

    target_rel = _child_relative_path(dir_rel, safe_name)

    if await adapter.exists(target_rel):
        raise HTTPException(
            status_code=409,
            detail=f"File already exists: {safe_name}",
        )

    max_size = get_settings().MAX_UPLOAD_FILE_SIZE_BYTES
    _reject_obviously_oversized_content_length(request, max_bytes=max_size)
    try:
        written = await adapter.write_file(target_rel, file.file, max_bytes=max_size)
    except DataConnectorWriteTooLargeError as exc:
        await _cleanup_uploaded_file(adapter, target_rel)
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds maximum size of {max_size} bytes",
        ) from exc

    content_item_id = compute_content_item_id(folder.uuid, target_rel)
    try:
        entry = await adapter.stat(target_rel)
    except FileNotFoundError:
        return _ok_response(path=target_rel, size=written)

    allowed, denied = await _effective_viewers(db, folder.uuid)

    await upsert_indexed_content_item(
        db,
        content_item_id,
        folder.uuid,
        target_rel,
        modified_time=entry.modified_time,
        change_time=entry.change_time,
        size_bytes=entry.size_bytes,
        allowed_viewers=allowed or None,
        denied_viewers=denied or None,
        status=determine_processing_status(None, folder),
        is_symlink=entry.is_symlink,
    )

    task_id = None
    processing_warning = None
    if folder.auto_process_new:
        metadata = _task_metadata(entry, content_item_id, source_name=folder.name)
        try:
            svc = TaskQueueService(db)
            task_id = await svc.enqueue_process(
                EnqueueProcessTask(
                    content_item_id=content_item_id,
                    folder_uuid=folder.uuid,
                    relative_path=target_rel,
                    metadata=metadata,
                    requested_by_sub=user.require_stable_sub(),
                ),
            )
        except Exception:
            logger.exception("Failed to enqueue uploaded file")
            processing_warning = (
                "File uploaded but automatic processing could not be started."
            )

    result = _ok_response(
        path=target_rel,
        size=written,
        content_item_id=content_item_id,
        task_id=task_id,
    )
    await ContentAuditService(db).append_event(
        content_item_id=content_item_id,
        connector_uuid=folder.uuid,
        relative_path=target_rel,
        display_name=safe_name,
        event_type="content.uploaded",
        event_group="content",
        status="completed",
        summary=f"Uploaded {safe_name}",
        metadata={"size_bytes": written, "task_id": task_id},
        user=user,
        source="ui",
        auto_commit=True,
    )
    if processing_warning:
        result["warning"] = processing_warning
    return result


@router.post("/mkdir")
async def create_directory(
    path: str = Query(
        ..., description="New directory path (folder_name/sub/path/new_dir)"
    ),
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Create a new directory (or S3 prefix marker).

    The path must start with a known folder name. The parent directory must
    already exist.  Hidden directory names (starting with ``"."``) are rejected.
    """
    stripped = path.strip("/")
    if not stripped:
        raise HTTPException(status_code=400, detail="Path is required")

    parts = stripped.rsplit("/", 1)
    if len(parts) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot create a top-level folder — provide a path inside an "
                "existing source"
            ),
        )

    parent_path, dir_name = parts
    if not dir_name or dir_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid directory name")

    folder, parent_rel = await resolve_authorized_source_dir(
        parent_path, user, file_service
    )
    _ensure_mutable_source(folder)
    adapter = folder.get_adapter()

    new_rel = _child_relative_path(parent_rel, dir_name)

    if await adapter.exists(new_rel):
        raise HTTPException(
            status_code=409,
            detail=f"Path already exists: {dir_name}",
        )

    await adapter.create_directory(new_rel)

    content_item_id = compute_content_item_id(folder.uuid, new_rel)
    allowed, denied = await _effective_viewers(db, folder.uuid)

    await upsert_directory_entry(
        db,
        content_item_id,
        folder.uuid,
        new_rel,
        allowed_viewers=allowed or None,
        denied_viewers=denied or None,
    )
    await ContentAuditService(db).append_event(
        content_item_id=content_item_id,
        connector_uuid=folder.uuid,
        relative_path=new_rel,
        display_name=dir_name,
        event_type="content.directory_created",
        event_group="content",
        status="completed",
        summary=f"Created directory {dir_name}",
        user=user,
        source="ui",
        auto_commit=True,
    )

    return _ok_response(path=new_rel, content_item_id=content_item_id)


@router.delete("/delete/{file_path:path}")
async def delete_file(
    file_path: str,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Delete a file from a data source.

    Removes the file via the source adapter, deletes the DB record,
    and cleans up any vector chunks and extracted data.
    """
    folder, rel_path = await resolve_authorized_source_file(
        file_path, user, file_service
    )
    _ensure_mutable_source(folder)
    adapter = folder.get_adapter()
    content_item_id = compute_content_item_id(folder.uuid, rel_path)
    display_name = Path(rel_path).name or rel_path

    try:
        await adapter.delete(rel_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    await ContentDeletionService(db).delete_content_path(
        folder_uuid=folder.uuid,
        relative_path=rel_path,
        content_item_id=content_item_id,
        display_name=display_name,
        user=user,
        source="ui",
    )

    return _ok_response(path=rel_path, content_item_id=content_item_id)
