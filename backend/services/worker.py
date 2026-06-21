"""Worker management service with SQLAlchemy (Async)."""

import hashlib
import json
import secrets
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlalchemy.future import select

from models.enums import TaskStatus
from models.sqlalchemy_models import TaskQueue, Worker
from models.worker import WorkerResponse, WorkerTaskQueueItem
from services.task_queue import TaskQueueService
from services.task_queue.shared import STALE_CLAIM_MINUTES
from services.utils import utcnow

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a raw API token."""
    return hashlib.sha256(token.encode()).hexdigest()


def _utc_isoformat(value: datetime | None) -> str | None:
    """Serialize UTC-naive DB timestamps with an explicit UTC offset."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _config_from_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        config = json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Ignoring invalid worker config JSON")
        return {}
    return config if isinstance(config, dict) else {}


def _config_to_json(config: dict) -> str:
    return json.dumps(config)


class WorkerService:
    """Manages worker CRUD and token storage in Postgres."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_worker_record(self, worker_id: str) -> Worker | None:
        """Fetch a Worker row by ID, or None."""
        stmt = select(Worker).where(Worker.id == worker_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _touch(worker: Worker) -> None:
        worker.updated_at = utcnow()

    async def create_token(self, worker_id: str) -> str:
        """Generate and store a new API token (hashed) for a worker."""
        token = secrets.token_urlsafe(32)
        worker = await self._get_worker_record(worker_id)

        if worker:
            worker.api_token = _hash_token(token)
            await self.db.commit()
            return token
        raise ValueError(f"Worker {worker_id} not found")

    async def revoke_token(self, worker_id: str) -> None:
        """Revoke the API token for a worker."""
        worker = await self._get_worker_record(worker_id)

        if worker:
            worker.api_token = None
            await self.db.commit()

    async def rotate_token(self, worker_id: str) -> str:
        """Revoke the old token and create a new one."""
        return await self.create_token(worker_id)

    async def validate_token(self, token: str) -> Optional[str]:
        """Look up a token (by hash) and return the worker_id, or None."""
        stmt = select(Worker.id).where(Worker.api_token == _hash_token(token))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_token(self, worker_id: str) -> Optional[str]:
        """Get the current token for a worker."""
        stmt = select(Worker.api_token).where(Worker.id == worker_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _model_to_response(worker: Worker) -> WorkerResponse:
        return WorkerResponse(
            id=worker.id,
            name=worker.name,
            description=worker.description,
            created_at=_utc_isoformat(worker.created_at) or "",
            updated_at=_utc_isoformat(worker.updated_at) or "",
            last_seen=_utc_isoformat(worker.last_seen),
            config=_config_from_json(worker.config),
            status=worker.status,
        )

    async def list_workers(self) -> list[WorkerResponse]:
        stmt = select(Worker).order_by(Worker.created_at.desc())
        result = await self.db.execute(stmt)
        workers = result.scalars().all()
        return [self._model_to_response(w) for w in workers]

    @staticmethod
    def _task_to_queue_item(
        task: TaskQueue, *, now: datetime | None = None
    ) -> WorkerTaskQueueItem:
        now_utc = _utc_datetime(now or utcnow())
        claimed_at_utc = _utc_datetime(task.claimed_at)
        stale_after_seconds = STALE_CLAIM_MINUTES * 60
        claim_age_seconds = (
            max(0, int((now_utc - claimed_at_utc).total_seconds()))
            if now_utc is not None and claimed_at_utc is not None
            else None
        )
        is_stale = (
            task.status == TaskStatus.CLAIMED
            and claim_age_seconds is not None
            and claim_age_seconds >= stale_after_seconds
        )
        return WorkerTaskQueueItem(
            id=task.id,
            task_type=task.task_type,
            content_kind=task.content_kind,
            content_item_id=task.content_item_id,
            folder_uuid=task.folder_uuid,
            relative_path=task.relative_path,
            status=task.status,
            stage=task.stage,
            requested_by_sub=task.requested_by_sub,
            claimed_by=task.claimed_by,
            claimed_at=_utc_isoformat(task.claimed_at),
            claim_age_seconds=claim_age_seconds,
            stale_after_seconds=stale_after_seconds,
            is_stale=is_stale,
            retry_count=task.retry_count or 0,
            max_retries=task.max_retries or 0,
            error_message=task.error_message,
            created_at=_utc_isoformat(task.created_at) or "",
            updated_at=_utc_isoformat(task.updated_at) or "",
        )

    async def list_queue_tasks(
        self, *, active_only: bool = True, limit: int = 50
    ) -> tuple[list[WorkerTaskQueueItem], int]:
        limit = max(1, min(limit, 200))
        filters = []
        if active_only:
            filters.append(
                TaskQueue.status.in_([TaskStatus.PENDING, TaskStatus.CLAIMED])
            )

        count_stmt = select(func.count(TaskQueue.id))
        stmt = select(TaskQueue)
        if filters:
            count_stmt = count_stmt.where(*filters)
            stmt = stmt.where(*filters)

        count_result = await self.db.execute(count_stmt)
        total = int(count_result.scalar() or 0)
        result = await self.db.execute(
            stmt.order_by(
                TaskQueue.updated_at.desc(), TaskQueue.created_at.desc()
            ).limit(limit)
        )
        tasks = result.scalars().all()
        now = utcnow()
        return [self._task_to_queue_item(task, now=now) for task in tasks], total

    async def cleanup_stale_tasks(self) -> dict[str, int]:
        return await TaskQueueService(self.db).cleanup_stale_claims_detailed()

    async def get_worker(self, worker_id: str) -> Optional[WorkerResponse]:
        worker = await self._get_worker_record(worker_id)
        if worker is None:
            return None
        return self._model_to_response(worker)

    async def create_worker(self, name: str, description: str = "") -> WorkerResponse:
        worker_id = str(uuid.uuid4())
        now = utcnow()
        worker = Worker(
            id=worker_id,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        self.db.add(worker)
        await self.db.commit()
        await self.db.refresh(worker)
        return self._model_to_response(worker)

    async def update_worker(
        self,
        worker_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[WorkerResponse]:
        worker = await self._get_worker_record(worker_id)
        if worker is None:
            return None

        if name is not None:
            worker.name = name
        if description is not None:
            worker.description = description

        self._touch(worker)
        await self.db.commit()
        await self.db.refresh(worker)
        return self._model_to_response(worker)

    async def delete_worker(self, worker_id: str) -> bool:
        worker = await self._get_worker_record(worker_id)
        if worker is None:
            return False

        await self.db.delete(worker)
        await self.db.commit()
        return True

    async def update_last_seen(self, worker_id: str) -> None:
        worker = await self._get_worker_record(worker_id)
        if worker:
            worker.last_seen = utcnow()
            worker.status = "active"
            self._touch(worker)
            await self.db.commit()

    async def update_config(self, worker_id: str, config: dict) -> None:
        worker = await self._get_worker_record(worker_id)
        if worker:
            worker.config = _config_to_json(config)
            self._touch(worker)
            await self.db.commit()
