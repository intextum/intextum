"""Internal task queue operation component."""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import ProcessingStatus, TaskStatus
from models.sqlalchemy_models import (
    TaskQueue,
)
from models.task_queue import (
    EnqueueProcessTask,
)
from .shared import (
    classify_worker_capability,
)
from services.utils import utcnow

if TYPE_CHECKING:
    from .service import TaskQueueService

logger = logging.getLogger(__name__)


class TaskQueueEnqueueOperations:
    """Task queue enqueueing operations isolated from worker lifecycle logic."""

    def __init__(self, service: TaskQueueService):
        self.service = service

    @property
    def db(self) -> AsyncSession:
        return self.service.db

    async def enqueue_process(
        self,
        request: EnqueueProcessTask,
        auto_commit: bool = True,
    ) -> str:
        worker_capability = classify_worker_capability(request.relative_path)
        now = utcnow()
        task_id = str(uuid.uuid4())
        task_secret = secrets.token_urlsafe(32)

        await self.db.execute(
            update(TaskQueue)
            .where(
                TaskQueue.content_item_id == request.content_item_id,
                TaskQueue.status == TaskStatus.PENDING,
            )
            .values(
                status=TaskStatus.SUPERSEDED,
                updated_at=now,
            )
        )

        task = TaskQueue(
            id=task_id,
            task_type="process",
            content_kind=worker_capability,
            content_item_id=request.content_item_id,
            folder_uuid=request.folder_uuid,
            relative_path=request.relative_path,
            metadata_json=request.metadata.model_dump_json(exclude_none=True),
            status=TaskStatus.PENDING,
            requested_by_sub=request.requested_by_sub,
            task_secret=task_secret,
            retry_count=0,
            max_retries=3,
            created_at=now,
            updated_at=now,
        )
        self.db.add(task)
        await self.db.flush()
        await self.service._set_queued_content_item(
            content_item_id=request.content_item_id,
            folder_uuid=request.folder_uuid,
            relative_path=request.relative_path,
            metadata=request.metadata,
            task_id=task_id,
            task_secret=task_secret,
        )
        await self.service._append_task_audit_event(
            task,
            event_type="content.processing.queued",
            status=ProcessingStatus.QUEUED.value,
            summary="Processing was queued",
            metadata={
                "worker_capability": worker_capability,
                "processing_config": request.metadata.processing_config,
            },
            actor_sub=request.requested_by_sub,
        )

        if auto_commit:
            await self.db.commit()
        logger.info(
            "Enqueued process task %s for %s (content_kind=%s)",
            task_id,
            request.relative_path,
            worker_capability,
        )
        return task_id
