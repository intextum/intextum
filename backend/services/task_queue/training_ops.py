"""Internal task queue operation component."""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.enums import TaskStatus
from models.sqlalchemy_models import (
    ContentChunk,
    IndexedContentItem,
    TaskQueue,
)
from models.task_queue import (
    ContentEnrichmentTrainingTaskMetadata,
)
from models.worker import (
    ContentEnrichmentSourceChunk,
    ContentEnrichmentTaskSourceResponse,
)
from .shared import (
    CONTENT_ENRICHMENT_TRAINING_TASK_TYPE,
    TRAINING_TASK_CONTENT_KIND,
    is_content_enrichment_training_task_type,
)
from .state import mark_task_completed
from services.utils import utcnow

if TYPE_CHECKING:
    from .service import TaskQueueService

logger = logging.getLogger(__name__)


class TaskQueueTrainingOperations:
    """Content-enrichment training and source payload operations."""

    def __init__(self, service: TaskQueueService):
        self.service = service

    @property
    def db(self) -> AsyncSession:
        return self.service.db

    async def get_content_enrichment_task_source(
        self, task_id: str, task_secret: str, worker_id: str | None = None
    ) -> ContentEnrichmentTaskSourceResponse | None:
        task = await self.service._get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None or task.task_type != "process":
            return None

        metadata = self.service._task_metadata(task)
        content_item_id = metadata.content_item_id or task.content_item_id
        if not isinstance(content_item_id, str) or not content_item_id.strip():
            return None
        if task.status != TaskStatus.CLAIMED:
            return None

        record_result = await self.db.execute(
            select(IndexedContentItem).where(
                IndexedContentItem.content_item_id == content_item_id
            )
        )
        record = record_result.scalar_one_or_none()
        if record is None:
            return None

        chunk_result = await self.db.execute(
            select(
                ContentChunk.chunk_index,
                ContentChunk.text,
                ContentChunk.page_numbers,
                ContentChunk.doc_refs,
                ContentChunk.images,
                ContentChunk.headings,
            )
            .where(ContentChunk.content_item_id == content_item_id)
            .order_by(ContentChunk.chunk_index)
        )
        chunks: list[ContentEnrichmentSourceChunk] = []
        for (
            chunk_index,
            text,
            page_numbers,
            doc_refs,
            images,
            headings,
        ) in chunk_result.all():
            if not isinstance(text, str) or not text.strip():
                continue
            chunks.append(
                ContentEnrichmentSourceChunk(
                    chunk_index=int(chunk_index or 0),
                    text=text,
                    page_numbers=[
                        int(value)
                        for value in (page_numbers or [])
                        if isinstance(value, int)
                    ],
                    doc_refs=[
                        value
                        for value in (doc_refs or [])
                        if isinstance(value, str) and value
                    ],
                    images=[
                        value
                        for value in (images or [])
                        if isinstance(value, str) and value
                    ],
                    headings=[
                        value
                        for value in (headings or [])
                        if isinstance(value, str) and value
                    ],
                )
            )

        current_document_class = (
            record.enrichment_state.classification_effective_label
            if record.enrichment_state is not None
            else None
        )

        return ContentEnrichmentTaskSourceResponse(
            task_id=task.id,
            content_item_id=content_item_id,
            relative_path=task.relative_path,
            current_document_class=current_document_class,
            chunks=chunks,
        )

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
        now = utcnow()
        task_id = str(uuid.uuid4())
        task_secret = secrets.token_urlsafe(32)
        metadata = ContentEnrichmentTrainingTaskMetadata(
            training_job_id=job_id,
            registry_model_id=registry_model_id,
            target_kind=target_kind,
            training_method=training_method,
            base_model=base_model,
            target_name=target_name,
            config_fingerprint=config_fingerprint,
            reviewed_example_count=reviewed_example_count,
            config_snapshot=config_snapshot,
        )
        task = TaskQueue(
            id=task_id,
            task_type=CONTENT_ENRICHMENT_TRAINING_TASK_TYPE,
            content_kind=TRAINING_TASK_CONTENT_KIND,
            content_item_id=registry_model_id,
            folder_uuid="__system__",
            relative_path=f"content-enrichment-training/{job_id}",
            metadata_json=metadata.model_dump_json(exclude_none=True),
            status=TaskStatus.PENDING,
            requested_by_sub=requested_by_sub,
            task_secret=task_secret,
            retry_count=0,
            max_retries=1,
            created_at=now,
            updated_at=now,
        )
        self.db.add(task)
        await self.db.flush()
        if auto_commit:
            await self.db.commit()
        logger.info(
            "Enqueued content enrichment training task %s for job %s (%s)",
            task_id,
            job_id,
            target_kind,
        )
        return task_id

    async def complete_content_enrichment_training_task(
        self,
        task_id: str,
        task_secret: str,
        *,
        artifact_path: str,
        metrics: dict[str, object] | None = None,
        worker_id: str | None = None,
    ) -> bool:
        task = await self.service._get_authorized_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None:
            return False
        if not is_content_enrichment_training_task_type(task.task_type):
            return False
        if task.status != TaskStatus.CLAIMED:
            return False

        normalized_artifact_path = artifact_path.strip()
        if not normalized_artifact_path:
            raise ValueError("artifact_path must be a non-empty string")

        now = utcnow()
        mark_task_completed(task, now=now)
        await self.service._update_training_job_status(
            task,
            job_status="completed",
            model_status="ready",
            error_message=None,
            artifact_path=normalized_artifact_path,
            metrics=metrics,
            completed_at=now,
            now=now,
        )
        await self.db.commit()
        logger.info("Training task %s completed", task_id)
        return True
