"""Helper functions for worker API router."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from config import BaseDataConnector
from models.enums import TaskStatus
from services.connector import ConnectorRuntimeService
from services.content.location import ContentLocation
from services.task_queue import TaskQueueService
from rls import set_rls_context, worker_task_context

logger = logging.getLogger(__name__)

FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{1,64}$")
CHUNK_SIZE = 1024 * 1024  # 1MB


@dataclass(frozen=True)
class WorkerFileRef:
    """Normalized folder-relative file reference for worker routes."""

    folder_uuid: str
    relative_path: str
    content_item_id: str


@dataclass(frozen=True)
class AuthorizedWorkerTask:
    """Task row resolved from a worker task secret."""

    task_id: str
    task_secret: str
    content_item_id: str
    folder_uuid: str
    relative_path: str


def assert_path_within_root(path: Path, root: Path) -> None:
    """Ensure `path` is contained in `root` after resolution."""
    try:
        path.relative_to(root.resolve())
    except ValueError as e:
        raise HTTPException(status_code=403, detail="Path traversal detected") from e


def parse_content_length(request: Request) -> int | None:
    """Parse Content-Length header if present and valid."""
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail="Invalid Content-Length header"
        ) from e
    if value < 0:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header")
    return value


def reject_oversized_content_length(
    request: Request,
    *,
    max_bytes: int,
    size_label: str,
) -> None:
    """Reject requests whose Content-Length already exceeds an upload limit."""
    content_length = parse_content_length(request)
    if content_length is not None and content_length > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Payload exceeds max {size_label} size of {max_bytes} bytes",
        )


async def write_upload_with_limit(
    upload: UploadFile, target: Path, max_bytes: int
) -> int:
    """Stream an upload to disk with hard byte limit and partial-file cleanup."""
    written = 0
    try:
        with open(target, "wb") as f:
            while chunk := await upload.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds max file size of {max_bytes} bytes",
                    )
                f.write(chunk)
    except Exception:
        _cleanup_partial_upload(target)
        raise
    return written


def _cleanup_partial_upload(target: Path) -> None:
    target.unlink(missing_ok=True)


async def get_folder(
    folder_uuid: str, db: AsyncSession | None = None
) -> BaseDataConnector:
    """Resolve a folder UUID to a data source, or raise 404.

    Runtime cache can get stale if sources are changed out-of-band. If a DB session
    is available, refresh cache once before returning 404.
    """
    runtime = ConnectorRuntimeService(db)
    folder = await runtime.get_connector_or_refresh(folder_uuid)
    if folder:
        return folder

    raise HTTPException(status_code=404, detail="Unknown folder UUID")


async def list_worker_folders(db: AsyncSession) -> list[BaseDataConnector]:
    """Refresh runtime sources and return folders visible to worker routes."""
    runtime = ConnectorRuntimeService(db)
    await runtime.refresh()
    return runtime.browsable_connectors()


def build_worker_file_ref(folder_uuid: str, file_path: str) -> WorkerFileRef:
    """Normalize a worker folder/file path into a deterministic file reference."""
    relative_path = file_path.strip("/")
    location = ContentLocation.from_parts(folder_uuid, relative_path)
    return WorkerFileRef(
        folder_uuid=folder_uuid,
        relative_path=location.relative_path,
        content_item_id=location.content_item_id,
    )


def validate_file_id(content_item_id: str) -> None:
    """Validate content_item_id is a hex string."""
    if not FILE_ID_PATTERN.match(content_item_id):
        raise HTTPException(status_code=400, detail="Invalid content_item_id format")


def _validated_batch_sub_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=400, detail="Each sub_path must be a non-empty string"
        )
    return value.strip("/")


def parse_batch_sub_paths(sub_paths: str, expected_count: int) -> list[str]:
    """Decode and validate `sub_paths` JSON list for batch upload."""
    try:
        parsed = json.loads(sub_paths)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400, detail="sub_paths must be valid JSON"
        ) from e

    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="sub_paths must be a JSON list")
    if len(parsed) != expected_count:
        raise HTTPException(
            status_code=400, detail="Number of sub_paths must match number of files"
        )

    return [_validated_batch_sub_path(value) for value in parsed]


def resolve_upload_target(base_dir: Path, sub_path: str) -> Path:
    """Resolve one upload target and enforce path containment."""
    target = (base_dir / sub_path).resolve()
    assert_path_within_root(target, base_dir)
    return target


def get_task_secret_header(request: Request) -> str:
    """Extract X-Task-Secret from request headers. Raises 401 if missing."""
    value = request.headers.get("x-task-secret")
    if not value:
        raise HTTPException(status_code=401, detail="Missing X-Task-Secret header")
    return value


def get_task_id_header(request: Request) -> str:
    """Extract X-Task-Id from request headers. Raises 401 if missing."""
    value = request.headers.get("x-task-id")
    if not value:
        raise HTTPException(status_code=401, detail="Missing X-Task-Id header")
    return value


async def require_task_access(
    content_item_id: str,
    task_secret: str,
    db: AsyncSession,
    *,
    worker_id: str | None = None,
) -> str:
    """Validate that a CLAIMED task exists for this content_item_id with matching secret.

    Raises 403 if no matching task is found.
    """
    task = await TaskQueueService(db).get_claimed_content_item_task(
        content_item_id,
        task_secret,
        worker_id=worker_id,
    )
    if task is not None:
        await set_rls_context(
            db,
            worker_task_context(
                worker_id=worker_id or "",
                task_id=task.id,
                content_item_id=content_item_id,
            ),
        )
        return task.id

    raise HTTPException(
        status_code=403,
        detail="Task secret does not match any active task for this content item",
    )


async def authorize_task_request(
    request: Request,
    *,
    content_item_id: str,
    db: AsyncSession,
    worker_id: str,
) -> str:
    """Extract task secret from request and validate access to one content_item_id."""
    task_secret = get_task_secret_header(request)
    await require_task_access(content_item_id, task_secret, db, worker_id=worker_id)
    return task_secret


async def authorize_task_request_for_content_item_ids(
    request: Request,
    *,
    content_item_ids: Iterable[str],
    db: AsyncSession,
    worker_id: str,
) -> str:
    """Extract one task secret and validate access to every referenced content_item_id."""
    task_secret = get_task_secret_header(request)
    for content_item_id in content_item_ids:
        await require_task_access(content_item_id, task_secret, db, worker_id=worker_id)
    return task_secret


async def authorize_claimed_process_task_request(
    request: Request,
    *,
    db: AsyncSession,
    worker_id: str,
) -> AuthorizedWorkerTask:
    """Resolve one claimed process task from request task id and secret."""
    task_id = get_task_id_header(request)
    task_secret = get_task_secret_header(request)
    task = await TaskQueueService(db).get_authorized_task(
        task_id, task_secret, worker_id=worker_id
    )
    if (
        task is None
        or task.task_type != "process"
        or not isinstance(task.content_item_id, str)
        or not task.content_item_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Task secret does not match any active processing task",
        )
    if task.status != TaskStatus.CLAIMED:
        raise HTTPException(
            status_code=409,
            detail=f"Processing task is no longer active: {task.status}",
        )
    await set_rls_context(
        db,
        worker_task_context(
            worker_id=worker_id,
            task_id=task_id,
            content_item_id=task.content_item_id,
        ),
    )
    return AuthorizedWorkerTask(
        task_id=task_id,
        task_secret=task_secret,
        content_item_id=task.content_item_id,
        folder_uuid=task.folder_uuid,
        relative_path=task.relative_path,
    )


async def authorize_extracted_upload(
    request: Request,
    *,
    content_item_id: str,
    db: AsyncSession,
    worker_id: str,
) -> AuthorizedWorkerTask:
    """Validate and authenticate an exact claimed task for extracted uploads."""
    validate_file_id(content_item_id)
    task = await authorize_claimed_process_task_request(
        request, db=db, worker_id=worker_id
    )
    if task.content_item_id != content_item_id:
        raise HTTPException(
            status_code=409,
            detail="Processing task does not match upload content item",
        )
    return task


async def resolve_authorized_worker_file(
    folder_uuid: str,
    file_path: str,
    request: Request,
    db: AsyncSession,
    worker_id: str,
) -> tuple[BaseDataConnector, WorkerFileRef]:
    """Resolve a worker source file and validate task-bound access to it."""
    file_ref = build_worker_file_ref(folder_uuid, file_path)
    await authorize_task_request(
        request,
        content_item_id=file_ref.content_item_id,
        db=db,
        worker_id=worker_id,
    )
    folder = await get_folder(folder_uuid, db)
    return folder, file_ref
