"""Internal task queue operation component."""

from __future__ import annotations

import inspect
import logging
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.enums import ProcessingStatus, TaskStatus
from models.sqlalchemy_models import (
    IndexedContentItem,
    TaskQueue,
)
from models.task_queue import (
    ClaimedTask,
    TaskFailureResult,
)
from rls import set_rls_context, worker_task_context
from services.ai_settings import AiSettingsService
from services.content.enrichment import complete_enrichment
from .artifacts import _processing_artifacts
from .shared import (
    STALE_CLAIM_MINUTES,
    VALID_WORKER_CAPABILITIES,
    is_content_enrichment_training_task_type,
)
from .state import (
    is_retryable_failure,
    mark_task_claimed,
    mark_task_completed,
    mark_task_failed,
    mark_task_requeued,
    mark_task_superseded,
    process_content_item_id,
    processing_claim_update_values,
    processing_completed_update_values,
    processing_failed_update_values,
    processing_retry_update_values,
    processing_revoked_update_values,
)
from services.utils import utcnow

if TYPE_CHECKING:
    from .service import TaskQueueService

logger = logging.getLogger(__name__)


class TaskQueueWorkerLifecycleOperations:
    """Claiming, completion, retries, and stale-claim repair operations."""

    def __init__(self, service: TaskQueueService):
        self.service = service

    @property
    def db(self) -> AsyncSession:
        return self.service.db

    async def _newer_active_task_id(self, task: TaskQueue) -> str | None:
        content_item_id = process_content_item_id(task)
        if not content_item_id or task.created_at is None:
            return None

        result = await self.db.execute(
            select(TaskQueue.id)
            .where(
                TaskQueue.content_item_id == content_item_id,
                TaskQueue.created_at > task.created_at,
                TaskQueue.status.in_([TaskStatus.PENDING, TaskStatus.CLAIMED]),
            )
            .limit(1)
        )
        task_id = result.scalar_one_or_none()
        if inspect.isawaitable(task_id):
            task_id = await task_id
        return task_id if isinstance(task_id, str) and task_id else None

    async def claim_task(
        self, worker_id: str, capabilities: list[str]
    ) -> ClaimedTask | None:
        if not capabilities:
            return None

        invalid = set(capabilities) - VALID_WORKER_CAPABILITIES
        if invalid:
            raise ValueError(f"Invalid capability types: {sorted(invalid)}")

        stmt = (
            select(TaskQueue)
            .where(
                TaskQueue.status == TaskStatus.PENDING,
                or_(
                    TaskQueue.content_kind.in_(capabilities),
                    TaskQueue.content_kind.is_(None),
                ),
            )
            .order_by(TaskQueue.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        result = await self.db.execute(stmt)
        task_row = result.scalar_one_or_none()
        if task_row is None:
            return None

        now = utcnow()
        mark_task_claimed(task_row, worker_id=worker_id, now=now)
        if task_row.content_item_id:
            await self.db.flush()
            await set_rls_context(
                self.db,
                worker_task_context(
                    worker_id=worker_id,
                    task_id=task_row.id,
                    content_item_id=task_row.content_item_id,
                ),
            )

        if is_content_enrichment_training_task_type(task_row.task_type):
            await self.service._update_training_job_status(
                task_row,
                job_status="running",
                model_status="training",
                started_at=now,
                completed_at=None,
                now=now,
            )
        else:
            await self.service._update_process_content_item(
                task_row,
                **processing_claim_update_values(worker_id=worker_id, now=now),
            )
            await self.service._append_task_audit_event(
                task_row,
                event_type="content.processing.started",
                status=ProcessingStatus.PROCESSING.value,
                summary="Processing was started",
                metadata={"worker_id": worker_id},
                actor_name=worker_id,
                source="worker",
            )

        await self.db.commit()

        logger.info(
            "Worker %s claimed task %s (%s)", worker_id, task_row.id, task_row.task_type
        )
        return self.service._task_response(task_row)

    async def complete_task(
        self,
        task_id: str,
        task_secret: str,
        processing_config: dict[str, object] | None = None,
        document_classification: dict[str, object] | None = None,
        document_extraction: dict[str, object] | None = None,
        worker_id: str | None = None,
    ) -> bool:
        task = await self.service._get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None:
            return False
        if task.status != TaskStatus.CLAIMED:
            logger.info(
                "Ignoring completion for task %s because status is %s",
                task_id,
                task.status,
            )
            return False

        now = utcnow()
        content_item_id = process_content_item_id(task)
        if await self._newer_active_task_id(task):
            _processing_artifacts().cleanup_task(task.id)
            mark_task_superseded(
                task,
                now=now,
                reason="Superseded by a newer processing task",
            )
            await self.db.commit()
            logger.info(
                "Ignoring completion for superseded task %s because a newer task is active",
                task_id,
            )
            return False

        promoted_document_json = None
        if content_item_id:
            promoted_document_json = _processing_artifacts().promote_staged_output(
                task_id=task.id,
                content_item_id=content_item_id,
            )

        mark_task_completed(task, now=now)

        if content_item_id:
            duration_ms = await self.service._processing_duration_ms(
                content_item_id, now
            )
            content_update_values = processing_completed_update_values(
                now=now,
                duration_ms=duration_ms,
                processing_config=processing_config,
            )
            if promoted_document_json is not None:
                content_update_values["document_json"] = promoted_document_json
            await self.service._update_indexed_content_item(
                content_item_id,
                **content_update_values,
            )
            if document_classification is not None or document_extraction is not None:
                record = (
                    await self.db.execute(
                        select(IndexedContentItem).where(
                            IndexedContentItem.content_item_id == content_item_id
                        )
                    )
                ).scalar_one_or_none()
                if record is not None:
                    effective_settings = await AiSettingsService(
                        self.db
                    ).get_effective_settings()
                    await complete_enrichment(
                        self.db,
                        record,
                        settings=effective_settings,
                        document_classification=document_classification,
                        document_extraction=document_extraction,
                    )
            await self.service._append_task_audit_event(
                task,
                event_type="content.processing.completed",
                status=ProcessingStatus.COMPLETED.value,
                summary="Processing completed",
                metadata={
                    "duration_ms": duration_ms,
                    "has_classification": document_classification is not None,
                    "has_extraction": document_extraction is not None,
                },
                source="worker",
            )

        logger.info("Task %s completed", task_id)
        await self.service._enqueue_task_event(
            task,
            kind="file.process.completed",
            status=ProcessingStatus.COMPLETED.value,
        )
        await self.db.commit()
        return True

    async def heartbeat_task(
        self,
        task_id: str,
        task_secret: str,
        worker_id: str | None = None,
        stage: str | None = None,
    ) -> bool:
        task = await self.service._get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None or task.status != TaskStatus.CLAIMED:
            return False

        now = utcnow()
        task.claimed_at = now
        task.updated_at = now
        if stage is not None and stage != task.stage:
            task.stage = stage
            task.stage_updated_at = now
            await self.service._update_process_content_item(
                task, processing_stage=stage
            )
        await self.db.commit()
        return True

    async def fail_task(
        self,
        task_id: str,
        task_secret: str,
        error_message: str,
        worker_id: str | None = None,
    ) -> TaskFailureResult | None:
        task = await self.service._get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None:
            return None
        if task.status != TaskStatus.CLAIMED:
            logger.info(
                "Ignoring failure for task %s because status is %s",
                task_id,
                task.status,
            )
            return None

        fatal_failure = error_message.startswith("FATAL:")
        is_training_task = is_content_enrichment_training_task_type(task.task_type)

        if is_retryable_failure(task, fatal_failure=fatal_failure):
            new_secret = secrets.token_urlsafe(32)
            now = utcnow()
            _processing_artifacts().cleanup_task(task.id)
            mark_task_requeued(
                task,
                now=now,
                new_secret=new_secret,
                error_message=error_message,
            )

            await self.service._update_process_content_item(
                task,
                **processing_retry_update_values(
                    error_message=error_message,
                    new_secret=new_secret,
                ),
            )
            if is_training_task:
                await self.service._update_training_job_status(
                    task,
                    job_status="queued",
                    model_status="training",
                    error_message=error_message,
                    started_at=None,
                    completed_at=None,
                    now=now,
                )

            await self.service._append_task_audit_event(
                task,
                event_type="content.processing.requeued",
                status=ProcessingStatus.RETRYING.value,
                summary="Processing was re-queued after a recoverable failure",
                metadata={"error": error_message, "retry_count": task.retry_count},
                source="worker",
            )
            await self.db.commit()
            logger.info(
                "Task %s re-queued (retry %d/%d)",
                task_id,
                task.retry_count,
                task.max_retries,
            )
            return TaskFailureResult(
                requeued=True,
                retry_count=task.retry_count,
                new_task_secret=new_secret,
            )

        now = utcnow()
        _processing_artifacts().cleanup_task(task.id)
        mark_task_failed(task, now=now, error_message=error_message)

        await self.service._update_process_content_item(
            task,
            **processing_failed_update_values(error_message=error_message),
        )
        if is_training_task:
            await self.service._update_training_job_status(
                task,
                job_status="failed",
                model_status="failed",
                error_message=error_message,
                completed_at=now,
                now=now,
            )
        if not is_training_task:
            await self.service._append_task_audit_event(
                task,
                event_type="content.processing.failed",
                status=ProcessingStatus.FAILED.value,
                summary="Processing failed",
                metadata={
                    "error": error_message,
                    "retry_count": task.retry_count,
                    "fatal": fatal_failure,
                },
                source="worker",
            )

        if not is_training_task:
            await self.service._enqueue_task_event(
                task,
                kind="file.process.failed",
                status=ProcessingStatus.FAILED.value,
            )
        await self.db.commit()
        if fatal_failure:
            logger.info("Task %s failed permanently due to fatal error", task_id)
        else:
            logger.info(
                "Task %s failed permanently after %d retries",
                task_id,
                task.max_retries,
            )
        return TaskFailureResult(
            requeued=False,
            retry_count=task.retry_count,
        )

    async def abort_task(
        self,
        task_id: str,
        task_secret: str,
        reason: str = "Aborted by worker or user",
        *,
        actor_sub: str | None = None,
        actor_name: str | None = None,
        source: str = "task_queue",
        worker_id: str | None = None,
    ) -> bool:
        task = await self.service._get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None:
            return False
        if task.status != TaskStatus.CLAIMED:
            logger.info(
                "Ignoring abort for task %s because status is %s",
                task_id,
                task.status,
            )
            return False

        now = utcnow()
        _processing_artifacts().cleanup_task(task.id)
        mark_task_superseded(task, now=now, reason=reason)

        await self.service._update_process_content_item(
            task,
            **processing_revoked_update_values(reason=reason),
        )
        if is_content_enrichment_training_task_type(task.task_type):
            await self.service._update_training_job_status(
                task,
                job_status="failed",
                model_status="failed",
                error_message=reason,
                completed_at=now,
                now=now,
            )
        await self.service._append_task_audit_event(
            task,
            event_type="content.processing.aborted",
            status=ProcessingStatus.REVOKED.value,
            summary="Processing was aborted",
            metadata={"reason": reason},
            actor_sub=actor_sub,
            actor_name=actor_name,
            source=source,
        )

        await self.db.commit()
        logger.info("Task %s explicitly aborted: %s", task_id, reason)
        return True

    async def is_superseded(
        self, task_id: str, task_secret: str, worker_id: str | None = None
    ) -> bool | None:
        task = await self.service._get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None:
            return None
        if task.status == TaskStatus.SUPERSEDED:
            return True

        return await self._newer_active_task_id(task) is not None

    async def cleanup_stale_claims_detailed(self) -> dict[str, int]:
        cutoff = utcnow() - timedelta(minutes=STALE_CLAIM_MINUTES)

        stmt = select(TaskQueue).where(
            TaskQueue.status == TaskStatus.CLAIMED,
            TaskQueue.claimed_at < cutoff,
        )
        result = await self.db.execute(stmt)
        stale_tasks = result.scalars().all()

        requeued_count = 0
        failed_count = 0
        for task in stale_tasks:
            now = utcnow()
            if task.retry_count < task.max_retries:
                await self.service._requeue_stale_task(task, now)
                requeued_count += 1
            else:
                await self.service._fail_stale_task(task, now)
                failed_count += 1

        if stale_tasks:
            await self.db.commit()

        if requeued_count or failed_count:
            logger.info(
                "Cleaned up %d stale tasks (%d re-queued, %d failed)",
                len(stale_tasks),
                requeued_count,
                failed_count,
            )
        return {
            "total": len(stale_tasks),
            "requeued": requeued_count,
            "failed": failed_count,
        }

    async def cleanup_stale_claims(self) -> int:
        result = await self.cleanup_stale_claims_detailed()
        return result["requeued"]
