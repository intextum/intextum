"""Worker management API router."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from auth.dependencies import require_admin
from models.user import User
from models.worker import (
    WorkerCreate,
    WorkerUpdate,
    WorkerResponse,
    WorkerCreateResponse,
    WorkerListResponse,
    WorkerTaskQueueCleanupResponse,
    WorkerTaskQueueListResponse,
)
from services.worker import WorkerService
from database import get_db
from rls import set_rls_context, user_context

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_worker_service(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> WorkerService:
    await set_rls_context(db, user_context(user))
    return WorkerService(db=db)


def _is_unique_constraint_error(exc: IntegrityError) -> bool:
    """Best-effort detection for duplicate-key errors across DB drivers."""
    message = str(getattr(exc, "orig", exc)).lower()
    return "unique" in message or "duplicate key" in message


@router.get("/", response_model=WorkerListResponse)
async def list_workers(
    service: WorkerService = Depends(get_worker_service),
):
    """List all registered workers."""
    workers = await service.list_workers()
    return WorkerListResponse(workers=workers, total=len(workers))


@router.get("/tasks", response_model=WorkerTaskQueueListResponse)
async def list_worker_tasks(
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    service: WorkerService = Depends(get_worker_service),
):
    """List processing/training queue tasks for admin visibility."""
    tasks, total = await service.list_queue_tasks(active_only=active_only, limit=limit)
    return WorkerTaskQueueListResponse(tasks=tasks, total=total)


@router.post("/tasks/cleanup-stale", response_model=WorkerTaskQueueCleanupResponse)
async def cleanup_stale_worker_tasks(
    service: WorkerService = Depends(get_worker_service),
):
    """Run stale claimed-task cleanup immediately."""
    return WorkerTaskQueueCleanupResponse(**await service.cleanup_stale_tasks())


@router.post(
    "/", response_model=WorkerCreateResponse, status_code=status.HTTP_201_CREATED
)
async def create_worker(
    body: WorkerCreate,
    service: WorkerService = Depends(get_worker_service),
):
    """Create a new worker and generate an API token."""
    try:
        worker = await service.create_worker(
            name=body.name, description=body.description
        )
    except IntegrityError as exc:
        await service.db.rollback()
        if _is_unique_constraint_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Worker with name '{body.name}' already exists",
            )
        raise exc
    token = await service.create_token(worker.id)
    return WorkerCreateResponse(worker=worker, token=token)


@router.get("/{worker_id}", response_model=WorkerResponse)
async def get_worker(
    worker_id: str,
    service: WorkerService = Depends(get_worker_service),
):
    """Get a single worker by ID."""
    worker = await service.get_worker(worker_id)
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found"
        )
    return worker


@router.put("/{worker_id}", response_model=WorkerResponse)
async def update_worker(
    worker_id: str,
    body: WorkerUpdate,
    service: WorkerService = Depends(get_worker_service),
):
    """Update worker name and/or description."""
    try:
        worker = await service.update_worker(
            worker_id, name=body.name, description=body.description
        )
    except IntegrityError as exc:
        await service.db.rollback()
        if _is_unique_constraint_error(exc):
            worker_name = body.name or worker_id
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Worker with name '{worker_name}' already exists",
            )
        raise exc
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found"
        )
    return worker


@router.delete("/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_worker(
    worker_id: str,
    service: WorkerService = Depends(get_worker_service),
):
    """Delete a worker and revoke its token."""
    deleted = await service.delete_worker(worker_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found"
        )
    return None


@router.post("/{worker_id}/rotate-token", response_model=WorkerCreateResponse)
async def rotate_token(
    worker_id: str,
    service: WorkerService = Depends(get_worker_service),
):
    """Rotate a worker's API token. Returns the new token (shown only once)."""
    worker = await service.get_worker(worker_id)
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found"
        )
    token = await service.rotate_token(worker_id)
    return WorkerCreateResponse(worker=worker, token=token)
