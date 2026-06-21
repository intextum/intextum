"""Internal task queue operation component."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.enums import ProcessingStatus, TaskStatus
from models.sqlalchemy_models import (
    ContentEnrichmentFineTuneJob,
    ContentEnrichmentModelRegistry,
    IndexedContentItem,
    TaskQueue,
)
from models.task_queue import (
    ProcessTaskMetadata,
)
from services.content.audit import ContentAuditService
from .artifacts import _processing_artifacts
from .shared import (
    STALE_CLAIM_FAILED_ERROR,
    STALE_CLAIM_RETRY_ERROR,
    STALE_CLAIM_TASK_ERROR,
    is_content_enrichment_training_task_type,
)
from .state import (
    apply_indexed_content_item_updates,
    mark_task_failed,
    mark_task_requeued,
    new_queued_indexed_content_item,
    process_content_item_id,
    processing_claim_update_values,
    processing_failed_update_values,
    processing_retry_update_values,
    queued_content_item_update_values,
)
from services.utils import utcnow

if TYPE_CHECKING:
    from .service import TaskQueueService

logger = logging.getLogger(__name__)


async def indexed_content_item_exists(
    db: AsyncSession,
    content_item_id: str,
) -> bool:
    result = await db.execute(
        select(IndexedContentItem.content_item_id).where(
            IndexedContentItem.content_item_id == content_item_id
        )
    )
    return result.scalar_one_or_none() is not None


class TaskQueueProcessStateOperations:
    """Indexed-content and training-job state mutation helpers."""

    def __init__(self, service: TaskQueueService):
        self.service = service

    @property
    def db(self) -> AsyncSession:
        return self.service.db

    async def set_queued_content_item(
        self,
        *,
        content_item_id: str,
        folder_uuid: str,
        relative_path: str,
        metadata: ProcessTaskMetadata,
        task_id: str,
        task_secret: str,
    ) -> None:
        result = await self.db.execute(
            select(IndexedContentItem).where(
                IndexedContentItem.content_item_id == content_item_id
            )
        )
        record = result.scalar_one_or_none()

        if record:
            update_values = queued_content_item_update_values(
                folder_uuid=folder_uuid,
                relative_path=relative_path,
                metadata=metadata,
                task_id=task_id,
                task_secret=task_secret,
            )
            if metadata.processing_config is not None:
                update_values["last_processing_config"] = metadata.processing_config
            apply_indexed_content_item_updates(record, **update_values)
            return

        record = new_queued_indexed_content_item(
            content_item_id=content_item_id,
            folder_uuid=folder_uuid,
            relative_path=relative_path,
            metadata=metadata,
            task_id=task_id,
            task_secret=task_secret,
        )
        self.db.add(record)
        await ContentAuditService(self.db).append_for_record(
            record,
            event_type="content.created",
            event_group="content",
            status="completed",
            summary=f"Content item created: {record.display_name or record.name or record.relative_path}",
            metadata={
                "content_kind": record.content_kind,
                "size_bytes": record.size_bytes,
                "processing_status": record.processing_status,
                "task_id": task_id,
            },
            source="task_queue",
        )

    async def update_indexed_content_item(
        self, content_item_id: str, **values: Any
    ) -> None:
        await self.db.execute(
            update(IndexedContentItem)
            .where(IndexedContentItem.content_item_id == content_item_id)
            .values(**values)
        )

    async def update_process_content_item(self, task: TaskQueue, **values: Any) -> None:
        content_item_id = process_content_item_id(task)
        if content_item_id:
            await self.update_indexed_content_item(content_item_id, **values)

    async def restore_claimed_process_content_item(
        self,
        *,
        content_item_id: str,
        task_secret: str,
        worker_id: str,
    ) -> bool:
        if await indexed_content_item_exists(self.db, content_item_id):
            return True

        task_result = await self.db.execute(
            select(TaskQueue)
            .where(
                TaskQueue.content_item_id == content_item_id,
                TaskQueue.task_type == "process",
                TaskQueue.status == TaskStatus.CLAIMED,
                TaskQueue.task_secret.is_not(None),
            )
            .order_by(TaskQueue.updated_at.desc())
        )
        for task in task_result.scalars().all():
            if not task.task_secret or not secrets.compare_digest(
                task.task_secret, task_secret
            ):
                continue

            now = utcnow()
            metadata = self.service._task_metadata(task)
            restored = new_queued_indexed_content_item(
                content_item_id=content_item_id,
                folder_uuid=task.folder_uuid,
                relative_path=task.relative_path,
                metadata=metadata,
                task_id=task.id,
                task_secret=task.task_secret,
            )
            apply_indexed_content_item_updates(
                restored,
                **processing_claim_update_values(worker_id=worker_id, now=now),
            )
            self.db.add(restored)
            await self.db.flush()
            logger.warning(
                "Restored missing indexed content item %s for claimed task %s",
                content_item_id,
                task.id,
            )
            return True

        return False

    async def update_training_job_status(
        self,
        task: TaskQueue,
        *,
        job_status: str,
        model_status: str | None = None,
        error_message: str | None = None,
        artifact_path: str | None = None,
        metrics: dict[str, object] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        now: datetime,
    ) -> None:
        metadata = self.service._training_task_metadata(task)
        if metadata is None:
            return

        job_values: dict[str, object | None] = {
            "status": job_status,
            "updated_at": now,
            "error_message": error_message,
        }
        if started_at is not None or job_status == "queued":
            job_values["started_at"] = started_at
        if completed_at is not None or job_status in {"queued", "running"}:
            job_values["completed_at"] = completed_at

        await self.db.execute(
            update(ContentEnrichmentFineTuneJob)
            .where(ContentEnrichmentFineTuneJob.id == metadata.training_job_id)
            .values(**job_values)
        )

        if model_status is None:
            return

        model_values: dict[str, object | None] = {
            "status": model_status,
            "updated_at": now,
        }
        if artifact_path is not None:
            model_values["artifact_path"] = artifact_path
        if metrics is not None:
            model_values["metrics_json"] = metrics

        await self.db.execute(
            update(ContentEnrichmentModelRegistry)
            .where(ContentEnrichmentModelRegistry.id == metadata.registry_model_id)
            .values(**model_values)
        )

    async def processing_duration_ms(
        self, content_item_id: str, now: datetime
    ) -> int | None:
        result = await self.db.execute(
            select(IndexedContentItem.processing_started_at).where(
                IndexedContentItem.content_item_id == content_item_id
            )
        )
        started_at = result.scalar_one_or_none()
        if started_at is None:
            return None
        delta = now - started_at
        return int(delta.total_seconds() * 1000)

    async def requeue_stale_task(self, task: TaskQueue, now: datetime) -> None:
        new_secret = secrets.token_urlsafe(32)
        _processing_artifacts().cleanup_task(task.id)
        mark_task_requeued(
            task,
            now=now,
            new_secret=new_secret,
            error_message=STALE_CLAIM_TASK_ERROR,
        )
        await self.service._update_process_content_item(
            task,
            **processing_retry_update_values(
                error_message=STALE_CLAIM_RETRY_ERROR,
                new_secret=new_secret,
            ),
        )
        if is_content_enrichment_training_task_type(task.task_type):
            await self.service._update_training_job_status(
                task,
                job_status="queued",
                model_status="training",
                error_message=STALE_CLAIM_RETRY_ERROR,
                started_at=None,
                completed_at=None,
                now=now,
            )
        await self.service._append_task_audit_event(
            task,
            event_type="content.processing.requeued",
            status=ProcessingStatus.RETRYING.value,
            summary="Processing was re-queued after a stale worker claim",
            metadata={
                "reason": STALE_CLAIM_RETRY_ERROR,
                "retry_count": task.retry_count,
            },
        )

    async def fail_stale_task(self, task: TaskQueue, now: datetime) -> None:
        _processing_artifacts().cleanup_task(task.id)
        mark_task_failed(
            task,
            now=now,
            error_message=STALE_CLAIM_FAILED_ERROR,
        )
        await self.service._update_process_content_item(
            task,
            **processing_failed_update_values(
                error_message=STALE_CLAIM_FAILED_ERROR,
            ),
        )
        if is_content_enrichment_training_task_type(task.task_type):
            await self.service._update_training_job_status(
                task,
                job_status="failed",
                model_status="failed",
                error_message=STALE_CLAIM_FAILED_ERROR,
                completed_at=now,
                now=now,
            )
        await self.service._append_task_audit_event(
            task,
            event_type="content.processing.failed",
            status=ProcessingStatus.FAILED.value,
            summary="Processing failed after stale worker claims",
            metadata={
                "error": STALE_CLAIM_FAILED_ERROR,
                "retry_count": task.retry_count,
            },
        )
