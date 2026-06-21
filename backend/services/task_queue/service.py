"""Async task queue service replacing Celery dispatch."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import TaskQueue
from models.task_queue import (
    ClaimedTask,
    ContentEnrichmentTrainingTaskMetadata,
    EnqueueProcessTask,
    ProcessTaskMetadata,
    TaskFailureResult,
)
from models.worker import ContentEnrichmentTaskSourceResponse
from .ops import (
    TaskQueueAccessOperations,
    TaskQueueEnqueueOperations,
    TaskQueueEventOperations,
    TaskQueueProcessStateOperations,
    TaskQueueTrainingOperations,
    TaskQueueWorkerLifecycleOperations,
)


class TaskQueueService:
    """Core task queue operations (async, requires AsyncSession)."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.access_ops = TaskQueueAccessOperations(self)
        self.event_ops = TaskQueueEventOperations(self)
        self.process_state_ops = TaskQueueProcessStateOperations(self)
        self.enqueue_ops = TaskQueueEnqueueOperations(self)
        self.training_ops = TaskQueueTrainingOperations(self)
        self.worker_lifecycle = TaskQueueWorkerLifecycleOperations(self)

    async def _set_queued_content_item(
        self,
        *,
        content_item_id: str,
        folder_uuid: str,
        relative_path: str,
        metadata: ProcessTaskMetadata,
        task_id: str,
        task_secret: str,
    ) -> None:
        await self.process_state_ops.set_queued_content_item(
            content_item_id=content_item_id,
            folder_uuid=folder_uuid,
            relative_path=relative_path,
            metadata=metadata,
            task_id=task_id,
            task_secret=task_secret,
        )

    async def _get_task(self, task_id: str) -> TaskQueue | None:
        return await self.access_ops.get_task(task_id)

    async def get_content_enrichment_task_source(
        self, task_id: str, task_secret: str, worker_id: str | None = None
    ) -> ContentEnrichmentTaskSourceResponse | None:
        return await self.training_ops.get_content_enrichment_task_source(
            task_id,
            task_secret,
            worker_id=worker_id,
        )

    def _display_file_path(self, task: TaskQueue) -> str:
        return self.event_ops.display_file_path(task)

    def _display_name(self, task: TaskQueue) -> str:
        return self.event_ops.display_name(task)

    async def _append_task_audit_event(
        self,
        task: TaskQueue,
        *,
        event_type: str,
        status: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
        actor_sub: str | None = None,
        actor_name: str | None = None,
        source: str = "task_queue",
    ) -> None:
        await self.event_ops.append_task_audit_event(
            task,
            event_type=event_type,
            status=status,
            summary=summary,
            metadata=metadata,
            actor_sub=actor_sub,
            actor_name=actor_name,
            source=source,
        )

    async def _enqueue_task_event(
        self, task: TaskQueue, *, kind: str, status: str
    ) -> None:
        await self.event_ops.enqueue_task_event(task, kind=kind, status=status)

    async def has_claimed_content_item_access(
        self,
        content_item_id: str,
        task_secret: str,
        worker_id: str | None = None,
    ) -> bool:
        return await self.access_ops.has_claimed_content_item_access(
            content_item_id,
            task_secret,
            worker_id=worker_id,
        )

    async def get_claimed_content_item_task(
        self,
        content_item_id: str,
        task_secret: str,
        worker_id: str | None = None,
    ) -> TaskQueue | None:
        return await self.access_ops.get_claimed_content_item_task(
            content_item_id,
            task_secret,
            worker_id=worker_id,
        )

    def _has_valid_secret(self, task: TaskQueue | None, task_secret: str) -> bool:
        return self.access_ops.has_valid_secret(task, task_secret)

    async def get_authorized_task(
        self, task_id: str, task_secret: str, worker_id: str | None = None
    ) -> TaskQueue | None:
        return await self.access_ops.get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )

    async def _get_authorized_task(
        self, task_id: str, task_secret: str, worker_id: str | None = None
    ) -> TaskQueue | None:
        return await self.access_ops.get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )

    def _task_metadata(self, task: TaskQueue) -> ProcessTaskMetadata:
        return self.access_ops.task_metadata(task)

    def _training_task_metadata(
        self,
        task: TaskQueue,
    ) -> ContentEnrichmentTrainingTaskMetadata | None:
        return self.access_ops.training_task_metadata(task)

    def _task_response(self, task: TaskQueue) -> ClaimedTask:
        return self.access_ops.task_response(task)

    async def _update_indexed_content_item(
        self, content_item_id: str, **values: Any
    ) -> None:
        await self.process_state_ops.update_indexed_content_item(
            content_item_id,
            **values,
        )

    async def _update_process_content_item(
        self, task: TaskQueue, **values: Any
    ) -> None:
        await self.process_state_ops.update_process_content_item(task, **values)

    async def restore_claimed_process_content_item(
        self,
        *,
        content_item_id: str,
        task_secret: str,
        worker_id: str,
    ) -> bool:
        return await self.process_state_ops.restore_claimed_process_content_item(
            content_item_id=content_item_id,
            task_secret=task_secret,
            worker_id=worker_id,
        )

    async def _update_training_job_status(
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
        await self.process_state_ops.update_training_job_status(
            task,
            job_status=job_status,
            model_status=model_status,
            error_message=error_message,
            artifact_path=artifact_path,
            metrics=metrics,
            started_at=started_at,
            completed_at=completed_at,
            now=now,
        )

    async def _processing_duration_ms(
        self, content_item_id: str, now: datetime
    ) -> int | None:
        return await self.process_state_ops.processing_duration_ms(content_item_id, now)

    async def _requeue_stale_task(self, task: TaskQueue, now: datetime) -> None:
        await self.process_state_ops.requeue_stale_task(task, now)

    async def _fail_stale_task(self, task: TaskQueue, now: datetime) -> None:
        await self.process_state_ops.fail_stale_task(task, now)

    async def enqueue_process(
        self,
        request: EnqueueProcessTask,
        auto_commit: bool = True,
    ) -> str:
        return await self.enqueue_ops.enqueue_process(request, auto_commit=auto_commit)

    async def enqueue_content_enrichment_training(
        self,
        *,
        job_id: str,
        registry_model_id: str,
        target_kind: str,
        training_method: str,
        base_model: str,
        target_name: str | None,
        config_fingerprint: str,
        reviewed_example_count: int,
        config_snapshot: dict[str, Any] | None,
        requested_by_sub: str | None,
        auto_commit: bool = True,
    ) -> str:
        return await self.training_ops.enqueue_content_enrichment_training(
            job_id=job_id,
            registry_model_id=registry_model_id,
            target_kind=target_kind,
            training_method=training_method,
            base_model=base_model,
            target_name=target_name,
            config_fingerprint=config_fingerprint,
            reviewed_example_count=reviewed_example_count,
            config_snapshot=config_snapshot,
            requested_by_sub=requested_by_sub,
            auto_commit=auto_commit,
        )

    async def claim_task(
        self, worker_id: str, capabilities: list[str]
    ) -> ClaimedTask | None:
        return await self.worker_lifecycle.claim_task(worker_id, capabilities)

    async def complete_task(
        self,
        task_id: str,
        task_secret: str,
        processing_config: dict[str, object] | None = None,
        document_classification: dict[str, object] | None = None,
        document_extraction: dict[str, object] | None = None,
        worker_id: str | None = None,
    ) -> bool:
        return await self.worker_lifecycle.complete_task(
            task_id,
            task_secret,
            processing_config=processing_config,
            document_classification=document_classification,
            document_extraction=document_extraction,
            worker_id=worker_id,
        )

    async def complete_content_enrichment_training_task(
        self,
        task_id: str,
        task_secret: str,
        *,
        artifact_path: str,
        metrics: dict[str, object] | None = None,
        worker_id: str | None = None,
    ) -> bool:
        return await self.training_ops.complete_content_enrichment_training_task(
            task_id,
            task_secret,
            artifact_path=artifact_path,
            metrics=metrics,
            worker_id=worker_id,
        )

    async def heartbeat_task(
        self,
        task_id: str,
        task_secret: str,
        worker_id: str | None = None,
        stage: str | None = None,
    ) -> bool:
        return await self.worker_lifecycle.heartbeat_task(
            task_id, task_secret, worker_id=worker_id, stage=stage
        )

    async def fail_task(
        self,
        task_id: str,
        task_secret: str,
        error_message: str,
        worker_id: str | None = None,
    ) -> TaskFailureResult | None:
        return await self.worker_lifecycle.fail_task(
            task_id,
            task_secret,
            error_message,
            worker_id=worker_id,
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
        return await self.worker_lifecycle.abort_task(
            task_id,
            task_secret,
            reason,
            actor_sub=actor_sub,
            actor_name=actor_name,
            source=source,
            worker_id=worker_id,
        )

    async def is_superseded(
        self, task_id: str, task_secret: str, worker_id: str | None = None
    ) -> bool | None:
        return await self.worker_lifecycle.is_superseded(
            task_id, task_secret, worker_id=worker_id
        )

    async def cleanup_stale_claims(self) -> int:
        return await self.worker_lifecycle.cleanup_stale_claims()

    async def cleanup_stale_claims_detailed(self) -> dict[str, int]:
        return await self.worker_lifecycle.cleanup_stale_claims_detailed()
