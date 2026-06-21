"""Internal task queue operation component."""

from __future__ import annotations

import json
import logging
import secrets
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.enums import TaskStatus
from models.sqlalchemy_models import (
    TaskQueue,
)
from models.task_queue import (
    ClaimedTask,
    ContentEnrichmentTrainingTaskMetadata,
    ProcessTaskMetadata,
)

if TYPE_CHECKING:
    from .service import TaskQueueService

logger = logging.getLogger(__name__)


def _metadata_payload_from_json(
    metadata_json: str | None, *, task_id: str | None = None
) -> dict[str, Any]:
    if not metadata_json:
        return {}

    try:
        payload = json.loads(metadata_json)
    except json.JSONDecodeError:
        logger.warning("Ignoring invalid metadata JSON for task %s", task_id)
        return {}

    return payload if isinstance(payload, dict) else {}


def task_metadata_payload(
    task: TaskQueue, *, include_content_item_id: bool = True
) -> dict[str, Any]:
    payload = _metadata_payload_from_json(task.metadata_json, task_id=task.id)
    if include_content_item_id and task.content_item_id:
        payload["content_item_id"] = task.content_item_id
    return payload


class TaskQueueAccessOperations:
    """Record lookup, authorization, and response-shaping helpers."""

    def __init__(self, service: TaskQueueService):
        self.service = service

    @property
    def db(self) -> AsyncSession:
        return self.service.db

    async def get_task(self, task_id: str) -> TaskQueue | None:
        result = await self.db.execute(select(TaskQueue).where(TaskQueue.id == task_id))
        return result.scalar_one_or_none()

    async def has_claimed_content_item_access(
        self, content_item_id: str, task_secret: str, worker_id: str | None = None
    ) -> bool:
        return (
            await self.get_claimed_content_item_task(
                content_item_id,
                task_secret,
                worker_id=worker_id,
            )
            is not None
        )

    async def get_claimed_content_item_task(
        self, content_item_id: str, task_secret: str, worker_id: str | None = None
    ) -> TaskQueue | None:
        filters = [
            TaskQueue.content_item_id == content_item_id,
            TaskQueue.status == TaskStatus.CLAIMED,
            TaskQueue.task_secret.is_not(None),
        ]
        if worker_id is not None:
            filters.append(TaskQueue.claimed_by == worker_id)
        result = await self.db.execute(select(TaskQueue).where(*filters))
        for task in result.scalars().all():
            if task.task_secret and secrets.compare_digest(
                task.task_secret, task_secret
            ):
                return task
        return None

    @staticmethod
    def has_valid_secret(task: TaskQueue | None, task_secret: str) -> bool:
        return bool(
            task
            and task.task_secret
            and secrets.compare_digest(task.task_secret, task_secret)
        )

    async def get_authorized_task(
        self, task_id: str, task_secret: str, worker_id: str | None = None
    ) -> TaskQueue | None:
        task = await self.get_task(task_id)
        if not self.has_valid_secret(task, task_secret):
            return None
        if worker_id is not None and getattr(task, "claimed_by", None) != worker_id:
            return None
        return task

    @staticmethod
    def _metadata_payload(task: TaskQueue) -> dict[str, Any]:
        return task_metadata_payload(task)

    @classmethod
    def task_metadata(cls, task: TaskQueue) -> ProcessTaskMetadata:
        payload = cls._metadata_payload(task)
        return ProcessTaskMetadata.model_validate(payload)

    @classmethod
    def training_task_metadata(
        cls,
        task: TaskQueue,
    ) -> ContentEnrichmentTrainingTaskMetadata | None:
        payload = cls._metadata_payload(task)
        try:
            return ContentEnrichmentTrainingTaskMetadata.model_validate(payload)
        except ValidationError:
            return None

    @classmethod
    def task_response(cls, task: TaskQueue) -> ClaimedTask:
        payload = cls._metadata_payload(task)
        return ClaimedTask(
            task_id=task.id,
            task_type=task.task_type,
            content_kind=task.content_kind,
            content_item_id=task.content_item_id,
            folder_uuid=task.folder_uuid,
            relative_path=task.relative_path,
            metadata=payload,
            task_secret=task.task_secret,
            retry_count=task.retry_count,
        )
