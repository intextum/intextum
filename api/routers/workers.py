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
    WorkerInstallInfo,
    WorkerInstallPlatform,
    WorkerListResponse,
    WorkerTaskQueueCleanupResponse,
    WorkerTaskQueueListResponse,
)
from services.worker import WorkerService
from services.general_settings import GeneralSettingsService
from database import get_db
from rls import set_rls_context, user_context
from version import get_app_version

router = APIRouter()
logger = logging.getLogger(__name__)

# Default capabilities a worker is started with (mirrors the compose default).
_DEFAULT_WORKER_CAPABILITIES = "document,video,image"

# GHCR namespace for the prebuilt worker images (REGISTRY/github.repository).
_WORKER_IMAGE_BASE = "ghcr.io/intextum/intextum"

_PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
_PYTORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu126"

# Install targets for the Add-Worker onboarding flow. macOS Torch wheels are on
# PyPI (no extra index); Linux/Windows CPU/CUDA builds come from the PyTorch
# index; Docker targets use the prebuilt GHCR images.
_WORKER_INSTALL_PLATFORMS: list[WorkerInstallPlatform] = [
    WorkerInstallPlatform(
        id="macos-mps",
        label="macOS (Apple Silicon · MPS)",
        kind="pip",
        extra="mps",
        notes="Uses Apple's native Vision OCR (ocrmac) and MPS acceleration.",
    ),
    WorkerInstallPlatform(
        id="linux-cpu",
        label="Linux (CPU)",
        kind="pip",
        extra="cpu",
        extra_index_url=_PYTORCH_CPU_INDEX,
    ),
    WorkerInstallPlatform(
        id="linux-cuda",
        label="Linux (NVIDIA CUDA 12.6)",
        kind="pip",
        extra="cuda",
        extra_index_url=_PYTORCH_CUDA_INDEX,
    ),
    WorkerInstallPlatform(
        id="windows-cpu",
        label="Windows (CPU)",
        kind="pip",
        extra="cpu",
        extra_index_url=_PYTORCH_CPU_INDEX,
    ),
    WorkerInstallPlatform(
        id="windows-cuda",
        label="Windows (NVIDIA CUDA 12.6)",
        kind="pip",
        extra="cuda",
        extra_index_url=_PYTORCH_CUDA_INDEX,
    ),
    WorkerInstallPlatform(
        id="docker-cpu",
        label="Docker (CPU)",
        kind="docker",
        image=f"{_WORKER_IMAGE_BASE}/worker-cpu",
    ),
    WorkerInstallPlatform(
        id="docker-cuda",
        label="Docker (NVIDIA CUDA)",
        kind="docker",
        image=f"{_WORKER_IMAGE_BASE}/worker-cuda",
        gpu=True,
    ),
]


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


@router.get("/install-info", response_model=WorkerInstallInfo)
async def get_install_info(
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return package/version + per-platform install targets for the Add-Worker UI.

    Declared before ``/{worker_id}`` so the static path is not captured as an id.
    """
    public_url = await GeneralSettingsService(db).get_public_base_url()
    return WorkerInstallInfo(
        package="intextum-worker",
        version=get_app_version(),
        default_capabilities=_DEFAULT_WORKER_CAPABILITIES,
        public_url=public_url,
        platforms=_WORKER_INSTALL_PLATFORMS,
    )


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
