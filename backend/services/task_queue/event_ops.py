"""Internal task queue operation component."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import (
    TaskQueue,
)
from services.content.audit import ContentAuditService
from services.event_outbox import EventOutboxService
from .state import (
    process_content_item_id,
)

if TYPE_CHECKING:
    from .service import TaskQueueService

logger = logging.getLogger(__name__)


class TaskQueueEventOperations:
    """Audit and user-event publication helpers."""

    def __init__(self, service: TaskQueueService):
        self.service = service

    @property
    def db(self) -> AsyncSession:
        return self.service.db

    def display_file_path(self, task: TaskQueue) -> str:
        metadata = self.service._task_metadata(task)
        if metadata.source_name:
            return f"{metadata.source_name}/{task.relative_path}"
        return task.relative_path

    @staticmethod
    def display_name(task: TaskQueue) -> str:
        return task.relative_path.rsplit("/", 1)[-1] or task.relative_path

    async def append_task_audit_event(
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
        content_item_id = process_content_item_id(task)
        if not content_item_id or task.task_type != "process":
            return
        await ContentAuditService(self.db).append_event(
            content_item_id=content_item_id,
            connector_uuid=task.folder_uuid,
            relative_path=task.relative_path,
            display_name=self.display_name(task),
            event_type=event_type,
            event_group="processing",
            status=status,
            summary=summary,
            metadata={
                "task_id": task.id,
                "file_path": self.display_file_path(task),
                **(metadata or {}),
            },
            actor_sub=actor_sub,
            actor_name=actor_name,
            source=source,
        )

    async def enqueue_task_event(
        self, task: TaskQueue, *, kind: str, status: str
    ) -> None:
        EventOutboxService(self.db).enqueue_user_event(
            user_sub=task.requested_by_sub,
            kind=kind,
            resource_type="file",
            resource_id=task.content_item_id or task.id,
            status=status,
            metadata={
                "task_id": task.id,
                "content_item_id": task.content_item_id,
                "file_path": self.display_file_path(task),
            },
        )
