"""Worker API task endpoints."""

import logging

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from auth.worker_auth import require_worker_token
from config import get_settings
from database import get_db
from models.content.enrichment_training import ContentEnrichmentWorkerTrainingDataset
from models.worker import (
    AbortTaskRequest,
    CheckSupersededRequest,
    ClaimTaskRequest,
    CompleteContentEnrichmentTrainingTaskRequest,
    CompleteTaskRequest,
    ContentEnrichmentTaskSourceResponse,
    ContentEnrichmentTrainingArtifactUploadResponse,
    FailTaskRequest,
    HeartbeatTaskRequest,
)
from rls import set_rls_context, worker_task_context
from routers.worker.helpers import (
    get_task_secret_header,
    reject_oversized_content_length,
    resolve_upload_target,
    write_upload_with_limit,
)
from services.content_enrichment_training import ContentEnrichmentTrainingService
from services.task_queue import TaskQueueService
from services.task_queue.shared import VALID_WORKER_CAPABILITIES

router = APIRouter()
logger = logging.getLogger(__name__)

_TASK_AUTH_ERROR_DETAIL = "Task not found or invalid secret"
WorkerTaskContextApplier = Callable[..., Awaitable[None]]


def _raise_task_auth_error() -> NoReturn:
    raise HTTPException(status_code=404, detail=_TASK_AUTH_ERROR_DETAIL)


def _ok_response() -> dict[str, str]:
    return {"status": "ok"}


async def _set_worker_task_context(
    *,
    db: AsyncSession,
    task_id: str,
    task_secret: str,
    worker_id: str,
) -> None:
    task = await TaskQueueService(db).get_authorized_task(
        task_id, task_secret, worker_id=worker_id
    )
    if task is None or not task.content_item_id:
        _raise_task_auth_error()
    await set_rls_context(
        db,
        worker_task_context(
            worker_id=worker_id,
            task_id=task_id,
            content_item_id=task.content_item_id,
        ),
    )


def get_worker_task_context_applier() -> WorkerTaskContextApplier:
    return _set_worker_task_context


@router.post("/tasks/claim")
async def claim_task(
    request: ClaimTaskRequest,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
):
    """Claim the next available task matching worker capabilities.

    Returns the task or 204 No Content if no task is available.
    """
    if not request.capabilities:
        raise HTTPException(status_code=400, detail="capabilities must not be empty")

    invalid = set(request.capabilities) - VALID_WORKER_CAPABILITIES
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid capability types: {sorted(invalid)}. Valid: {sorted(VALID_WORKER_CAPABILITIES)}",
        )

    svc = TaskQueueService(db)
    task = await svc.claim_task(worker_id, request.capabilities)

    if task is None:
        return Response(status_code=204)

    return task.model_dump(mode="json")


@router.get(
    "/tasks/{task_id}/content-enrichment-training-dataset",
    response_model=ContentEnrichmentWorkerTrainingDataset,
)
async def get_content_enrichment_training_dataset(
    task_id: str,
    request: Request,
    _worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Return the reviewed GLiNER2 training dataset for one claimed training task."""
    task_secret = get_task_secret_header(request)
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=task_secret, worker_id=_worker_id
    )
    dataset = await ContentEnrichmentTrainingService(db).get_worker_training_dataset(
        task_id,
        task_secret,
        worker_id=_worker_id,
    )
    if dataset is None:
        _raise_task_auth_error()
    return dataset


@router.get(
    "/tasks/{task_id}/content-enrichment-source",
    response_model=ContentEnrichmentTaskSourceResponse,
)
async def get_content_enrichment_task_source(
    task_id: str,
    request: Request,
    _worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Return stored chunks and effective class for one claimed enrichment rerun task."""
    task_secret = get_task_secret_header(request)
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=task_secret, worker_id=_worker_id
    )
    source = await TaskQueueService(db).get_content_enrichment_task_source(
        task_id,
        task_secret,
        worker_id=_worker_id,
    )
    if source is None:
        _raise_task_auth_error()
    return source


@router.post(
    "/tasks/{task_id}/content-enrichment-training-artifact",
    response_model=ContentEnrichmentTrainingArtifactUploadResponse,
)
async def upload_content_enrichment_training_artifact(
    task_id: str,
    request: Request,
    file: UploadFile = File(...),
    _worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Upload one adapter artifact bundle for a claimed training task."""
    task_secret = get_task_secret_header(request)
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=task_secret, worker_id=_worker_id
    )
    svc = ContentEnrichmentTrainingService(db)
    try:
        target = await svc.get_worker_training_artifact_upload_target(
            task_id,
            task_secret,
            filename=file.filename,
            worker_id=_worker_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if target is None:
        _raise_task_auth_error()

    settings = get_settings()
    max_file_size = settings.MAX_MODEL_ARTIFACT_UPLOAD_SIZE_BYTES
    reject_oversized_content_length(request, max_bytes=max_file_size, size_label="file")

    artifacts_root = Path(settings.MODEL_ARTIFACTS_DIR)
    target_path = resolve_upload_target(artifacts_root, target.artifact_path)
    tmp_target: Path | None = None
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_target = resolve_upload_target(
            target_path.parent, f".{target_path.name}.upload"
        )
        size = await write_upload_with_limit(file, tmp_target, max_file_size)
        tmp_target.replace(target_path)
    except OSError as exc:
        if tmp_target is not None:
            tmp_target.unlink(missing_ok=True)
        logger.exception(
            "Failed to persist content enrichment training artifact",
            extra={
                "task_id": task_id,
                "registry_model_id": target.registry_model_id,
                "artifacts_root": str(artifacts_root),
                "artifact_path": target.artifact_path,
            },
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to store model artifact. "
                f"Check MODEL_ARTIFACTS_DIR permissions for '{artifacts_root}'."
            ),
        ) from exc

    return ContentEnrichmentTrainingArtifactUploadResponse(
        status="ok",
        registry_model_id=target.registry_model_id,
        artifact_path=target.artifact_path,
        size=size,
    )


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    request: CompleteTaskRequest,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Mark a task as completed. Requires the per-task secret."""
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=request.task_secret, worker_id=worker_id
    )
    svc = TaskQueueService(db)
    ok = await svc.complete_task(
        task_id,
        request.task_secret,
        processing_config=request.processing_config,
        document_classification=request.document_classification,
        document_extraction=request.document_extraction,
        worker_id=worker_id,
    )
    if not ok:
        _raise_task_auth_error()
    return _ok_response()


@router.post("/tasks/{task_id}/content-enrichment-training-complete")
async def complete_content_enrichment_training_task(
    task_id: str,
    request: CompleteContentEnrichmentTrainingTaskRequest,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Mark a training task complete and promote its registry entry."""
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=request.task_secret, worker_id=worker_id
    )
    svc = TaskQueueService(db)
    try:
        ok = await svc.complete_content_enrichment_training_task(
            task_id,
            request.task_secret,
            artifact_path=request.artifact_path,
            metrics=request.metrics,
            worker_id=worker_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        _raise_task_auth_error()
    return _ok_response()


@router.post("/tasks/{task_id}/heartbeat")
async def heartbeat_task(
    task_id: str,
    request: HeartbeatTaskRequest,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Refresh the claim heartbeat timestamp for an active task."""
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=request.task_secret, worker_id=worker_id
    )
    svc = TaskQueueService(db)
    ok = await svc.heartbeat_task(
        task_id, request.task_secret, worker_id=worker_id, stage=request.stage
    )
    if not ok:
        _raise_task_auth_error()
    return _ok_response()


@router.post("/tasks/{task_id}/fail")
async def fail_task(
    task_id: str,
    request: FailTaskRequest,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Report a task failure. Backend handles retry logic."""
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=request.task_secret, worker_id=worker_id
    )
    svc = TaskQueueService(db)
    result = await svc.fail_task(
        task_id,
        request.task_secret,
        request.error_message,
        worker_id=worker_id,
    )
    if result is None:
        _raise_task_auth_error()
    return result.model_dump(mode="json", exclude_none=True)


@router.post("/tasks/{task_id}/abort")
async def abort_task_endpoint(
    task_id: str,
    request: AbortTaskRequest,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Explicitly abort a task."""
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=request.task_secret, worker_id=worker_id
    )
    svc = TaskQueueService(db)
    ok = await svc.abort_task(
        task_id,
        request.task_secret,
        request.reason or "Aborted by worker",
        actor_name=worker_id,
        source="worker",
        worker_id=worker_id,
    )
    if not ok:
        _raise_task_auth_error()
    return _ok_response()


@router.post("/tasks/{task_id}/superseded")
async def check_superseded(
    task_id: str,
    request: CheckSupersededRequest,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
    apply_worker_task_context: WorkerTaskContextApplier = Depends(
        get_worker_task_context_applier
    ),
):
    """Check if a task has been superseded by a newer task for the same file."""
    await apply_worker_task_context(
        db=db, task_id=task_id, task_secret=request.task_secret, worker_id=worker_id
    )
    svc = TaskQueueService(db)
    result = await svc.is_superseded(task_id, request.task_secret, worker_id=worker_id)
    if result is None:
        _raise_task_auth_error()
    return {"superseded": result}
