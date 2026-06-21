"""Service layer for content enrichment fine-tune jobs and model registry entries."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_settings import EffectiveAiSettings
from models.content.enrichment_training import (
    CreateContentEnrichmentFineTuneJobRequest,
    ContentEnrichmentFineTuneJobEntry,
    ContentEnrichmentModelPromotionResponse,
    ContentEnrichmentModelRegistryEntry,
    ContentEnrichmentTrainingCurrentExamples,
    ContentEnrichmentTrainingOverviewResponse,
    ContentEnrichmentWorkerRegistryModel,
    ContentEnrichmentWorkerTrainingDataset,
)
from models.enums import TaskStatus
from models.sqlalchemy_models import (
    ContentEnrichmentFineTuneJob,
    ContentEnrichmentModelRegistry,
    TaskQueue,
)
from services.ai_settings import AiSettingsService
from services.task_queue import TaskQueueService
from services.task_queue.access_ops import task_metadata_payload
from services.task_queue.shared import is_content_enrichment_training_task_type
from services.task_queue.state import mark_task_failed
from services.utils import utcnow
from .dataset import ContentEnrichmentTrainingDatasetBuilder
from .presenters import job_entry, model_entry
from .refs import parse_content_enrichment_registry_model_ref
from .registry import ContentEnrichmentTrainingRegistry


@dataclass(frozen=True)
class ContentEnrichmentTrainingArtifactUploadTarget:
    """Resolved backend artifact destination for one claimed training task."""

    registry_model_id: str
    artifact_path: str
    filename: str


class ContentEnrichmentTrainingService:
    """Create and list queued content enrichment adapter training jobs."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = ContentEnrichmentTrainingRegistry(db)
        self.dataset_builder = ContentEnrichmentTrainingDatasetBuilder(db)

    @staticmethod
    def _config_fingerprint(
        settings: EffectiveAiSettings,
    ) -> str:
        return ContentEnrichmentTrainingRegistry.config_fingerprint(settings)

    @staticmethod
    def _config_snapshot(
        settings: EffectiveAiSettings,
    ) -> dict[str, Any]:
        return ContentEnrichmentTrainingRegistry.config_snapshot(settings)

    async def _load_registry_model_row(
        self, model_id: str
    ) -> ContentEnrichmentModelRegistry | None:
        return await self.registry.load_registry_model_row(model_id)

    async def _load_job_row(self, job_id: str) -> ContentEnrichmentFineTuneJob | None:
        return await self.registry.load_job_row(job_id)

    async def _load_queue_task_row(self, task_id: str | None) -> TaskQueue | None:
        return await self.registry.load_queue_task_row(task_id)

    async def _active_model_ids(self) -> set[str]:
        return await self.registry.active_model_ids()

    @staticmethod
    def _promoted_effective_settings(
        settings: EffectiveAiSettings,
        *,
        setting_value: str,
    ) -> EffectiveAiSettings:
        return ContentEnrichmentTrainingRegistry.promoted_effective_settings(
            settings,
            setting_value=setting_value,
        )

    async def _stale_file_count_for_settings(
        self,
        settings: EffectiveAiSettings,
    ) -> int:
        return await self.registry.stale_file_count_for_settings(settings)

    async def _resolved_training_base_model(
        self,
        request: CreateContentEnrichmentFineTuneJobRequest,
        settings: EffectiveAiSettings,
    ) -> str:
        return await self.registry.resolved_training_base_model(request, settings)

    @staticmethod
    def _validate_request(
        request: CreateContentEnrichmentFineTuneJobRequest,
        settings: EffectiveAiSettings,
    ) -> None:
        ContentEnrichmentTrainingRegistry.validate_request(request, settings)

    @staticmethod
    def _validate_reviewed_example_count(
        reviewed_example_count: int,
    ) -> None:
        ContentEnrichmentTrainingRegistry.validate_reviewed_example_count(
            reviewed_example_count,
        )

    async def _reviewed_example_count(self) -> int:
        return await self.dataset_builder.reviewed_example_count()

    async def _current_reviewed_examples(
        self,
    ) -> ContentEnrichmentTrainingCurrentExamples:
        classification = await self._reviewed_example_count()
        return ContentEnrichmentTrainingCurrentExamples(classification=classification)

    async def _load_authorized_training_task(
        self,
        task_id: str,
        task_secret: str,
        *,
        worker_id: str | None = None,
    ) -> TaskQueue | None:
        result = await self.db.execute(select(TaskQueue).where(TaskQueue.id == task_id))
        task = result.scalar_one_or_none()
        if task is None or not task.task_secret:
            return None
        if not secrets.compare_digest(task.task_secret, task_secret):
            return None
        if not is_content_enrichment_training_task_type(task.task_type):
            return None
        if task.status != TaskStatus.CLAIMED:
            return None
        if worker_id is not None and getattr(task, "claimed_by", None) != worker_id:
            return None
        return task

    @staticmethod
    def _task_metadata(task: TaskQueue) -> dict[str, Any]:
        return task_metadata_payload(task, include_content_item_id=False)

    @staticmethod
    def _normalize_artifact_filename(filename: str | None) -> str:
        candidate = Path(filename or "").name.strip()
        if not candidate or candidate in {".", ".."}:
            return "adapter.tar.gz"
        return candidate

    @staticmethod
    def _cancel_message(cancelled_by: str | None) -> str:
        return (
            f"Cancelled by {cancelled_by}"
            if isinstance(cancelled_by, str) and cancelled_by
            else "Cancelled by admin"
        )

    @staticmethod
    def _mark_queue_task_cancelled(
        queue_task: TaskQueue | None,
        *,
        now: datetime,
        message: str,
    ) -> None:
        if queue_task is None or queue_task.status not in {
            TaskStatus.PENDING,
            TaskStatus.CLAIMED,
        }:
            return
        mark_task_failed(queue_task, now=now, error_message=message)
        queue_task.claimed_by = None
        queue_task.claimed_at = None

    @staticmethod
    def _mark_job_cancelled(
        job_row: ContentEnrichmentFineTuneJob,
        *,
        now: datetime,
        message: str,
    ) -> None:
        job_row.status = "failed"
        job_row.error_message = message
        job_row.completed_at = now
        job_row.updated_at = now

    @staticmethod
    def _mark_registry_model_failed(
        model_row: ContentEnrichmentModelRegistry,
        *,
        now: datetime,
    ) -> None:
        model_row.status = "failed"
        model_row.updated_at = now

    async def get_overview(self) -> ContentEnrichmentTrainingOverviewResponse:
        effective_settings = await AiSettingsService(self.db).get_effective_settings()
        active_classification_id = parse_content_enrichment_registry_model_ref(
            effective_settings.document_classification_model
        )
        current_examples = await self._current_reviewed_examples()
        jobs_result = await self.db.execute(
            select(ContentEnrichmentFineTuneJob).order_by(
                ContentEnrichmentFineTuneJob.created_at.desc()
            )
        )
        models_result = await self.db.execute(
            select(ContentEnrichmentModelRegistry).order_by(
                ContentEnrichmentModelRegistry.created_at.desc()
            )
        )
        return ContentEnrichmentTrainingOverviewResponse(
            jobs=[job_entry(row) for row in jobs_result.scalars().all()],
            models=[
                model_entry(
                    row,
                    is_active=(row.id == active_classification_id),
                )
                for row in models_result.scalars().all()
            ],
            current_examples=current_examples,
        )

    async def get_worker_training_dataset(
        self,
        task_id: str,
        task_secret: str,
        *,
        worker_id: str | None = None,
    ) -> ContentEnrichmentWorkerTrainingDataset | None:
        task = await self._load_authorized_training_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None:
            return None
        return await self.dataset_builder.build_worker_training_dataset(task)

    async def get_worker_training_artifact_upload_target(
        self,
        task_id: str,
        task_secret: str,
        *,
        filename: str | None,
        worker_id: str | None = None,
    ) -> ContentEnrichmentTrainingArtifactUploadTarget | None:
        """Return the storage target for one claimed training artifact upload."""
        task = await self._load_authorized_training_task(
            task_id, task_secret, worker_id=worker_id
        )
        if task is None:
            return None

        metadata = self._task_metadata(task)
        registry_model_id = str(metadata.get("registry_model_id") or "").strip()
        if not registry_model_id:
            raise ValueError("Training task is missing registry_model_id metadata")

        safe_filename = self._normalize_artifact_filename(filename)
        artifact_path = f"content-enrichment/{registry_model_id}/{safe_filename}"
        return ContentEnrichmentTrainingArtifactUploadTarget(
            registry_model_id=registry_model_id,
            artifact_path=artifact_path,
            filename=safe_filename,
        )

    async def create_job(
        self,
        request: CreateContentEnrichmentFineTuneJobRequest,
        *,
        requested_by: str | None,
        requested_by_sub: str | None,
    ) -> ContentEnrichmentFineTuneJobEntry:
        settings = await AiSettingsService(self.db).get_effective_settings()
        self._validate_request(request, settings)

        base_model = await self._resolved_training_base_model(request, settings)
        config_fingerprint = self._config_fingerprint(settings)
        reviewed_example_count = await self._reviewed_example_count()
        self._validate_reviewed_example_count(reviewed_example_count)
        config_snapshot = self._config_snapshot(settings)

        model_row = ContentEnrichmentModelRegistry(
            id=str(uuid.uuid4()),
            target_kind=request.target_kind,
            training_method=request.training_method,
            status="training",
            base_model=base_model,
            target_name=request.target_name,
            config_fingerprint=config_fingerprint,
            reviewed_example_count=reviewed_example_count,
            created_by=requested_by,
        )
        self.db.add(model_row)
        await self.db.flush()

        job_row = ContentEnrichmentFineTuneJob(
            id=str(uuid.uuid4()),
            registry_model_id=model_row.id,
            status="queued",
            target_kind=request.target_kind,
            training_method=request.training_method,
            base_model=base_model,
            target_name=request.target_name,
            config_fingerprint=config_fingerprint,
            dataset_summary_json={
                "reviewed_example_count": reviewed_example_count,
            },
            config_snapshot_json=config_snapshot,
            requested_by=requested_by,
            requested_by_sub=requested_by_sub,
        )
        self.db.add(job_row)
        await self.db.flush()

        task_id = await TaskQueueService(self.db).enqueue_content_enrichment_training(
            job_id=job_row.id,
            registry_model_id=model_row.id,
            target_kind=request.target_kind,
            training_method=request.training_method,
            base_model=base_model,
            target_name=request.target_name,
            config_fingerprint=config_fingerprint,
            reviewed_example_count=reviewed_example_count,
            config_snapshot=config_snapshot,
            requested_by_sub=requested_by_sub,
            auto_commit=False,
        )
        job_row.queue_task_id = task_id

        await self.db.commit()
        await self.db.refresh(job_row)
        return job_entry(job_row)

    async def retry_job(
        self,
        job_id: str,
        *,
        requested_by: str | None,
        requested_by_sub: str | None,
    ) -> ContentEnrichmentFineTuneJobEntry:
        """Queue one fresh training job using the same scope as a failed job."""
        job_row = await self._load_job_row(job_id)
        if job_row is None:
            raise LookupError("Unknown content enrichment training job")
        if job_row.status != "failed":
            raise ValueError("Only failed training jobs can be retried")
        return await self.create_job(
            CreateContentEnrichmentFineTuneJobRequest(
                target_kind="classification",
                training_method=job_row.training_method,
                base_model=job_row.base_model,
            ),
            requested_by=requested_by,
            requested_by_sub=requested_by_sub,
        )

    async def cancel_job(
        self,
        job_id: str,
        *,
        cancelled_by: str | None,
    ) -> ContentEnrichmentFineTuneJobEntry:
        """Cancel one queued or running training job."""
        job_row = await self._load_job_row(job_id)
        if job_row is None:
            raise LookupError("Unknown content enrichment training job")
        if job_row.status not in {"queued", "running"}:
            raise ValueError("Only queued or running training jobs can be cancelled")

        registry_model = await self._load_registry_model_row(job_row.registry_model_id)
        if registry_model is None:
            raise LookupError("Unknown content enrichment model")

        now = utcnow()
        cancel_message = self._cancel_message(cancelled_by)

        queue_task = await self._load_queue_task_row(job_row.queue_task_id)
        self._mark_queue_task_cancelled(
            queue_task,
            now=now,
            message=cancel_message,
        )
        self._mark_job_cancelled(job_row, now=now, message=cancel_message)
        self._mark_registry_model_failed(registry_model, now=now)

        await self.db.commit()
        await self.db.refresh(job_row)
        return job_entry(job_row)

    async def delete_job(self, job_id: str) -> None:
        """Remove one failed or cancelled training job from the history."""
        job_row = await self._load_job_row(job_id)
        if job_row is None:
            raise LookupError("Unknown content enrichment training job")
        if job_row.status != "failed":
            raise ValueError("Only failed or cancelled training jobs can be removed")

        queue_task = await self._load_queue_task_row(job_row.queue_task_id)
        if queue_task is not None and queue_task.status == TaskStatus.FAILED:
            await self.db.delete(queue_task)

        registry_model = await self._load_registry_model_row(job_row.registry_model_id)
        active_ids = await self._active_model_ids()
        registry_deletable = (
            registry_model is not None
            and registry_model.id not in active_ids
            and registry_model.status in {"failed", "training"}
        )
        if registry_deletable:
            # FK ON DELETE CASCADE on registry_model_id removes the job row too.
            await self.db.delete(registry_model)
        else:
            await self.db.delete(job_row)

        await self.db.commit()

    async def archive_model(
        self,
        model_id: str,
    ) -> ContentEnrichmentModelRegistryEntry:
        """Archive one inactive ready or failed registry model."""
        model_row = await self._load_registry_model_row(model_id)
        if model_row is None:
            raise LookupError("Unknown content enrichment model")
        if model_row.status == "archived":
            return model_entry(model_row, is_active=False)
        if model_row.status not in {"ready", "failed"}:
            raise ValueError("Only ready or failed models can be archived")
        if model_row.id in await self._active_model_ids():
            raise ValueError("Active models cannot be archived")

        model_row.status = "archived"
        await self.db.commit()
        await self.db.refresh(model_row)
        return model_entry(model_row, is_active=False)

    async def promote_model(
        self,
        model_id: str,
        *,
        updated_by: str | None,
    ) -> ContentEnrichmentModelPromotionResponse:
        """Promote one ready registry model into the live AI settings."""
        model_row = await self._load_registry_model_row(model_id)
        if model_row is None:
            raise LookupError("Unknown content enrichment model")
        if model_row.status != "ready":
            raise ValueError("Only ready models can be promoted")
        normalized_artifact_path = (
            model_row.artifact_path.strip()
            if isinstance(model_row.artifact_path, str)
            else ""
        )
        if not normalized_artifact_path:
            raise ValueError("Cannot promote a model without an uploaded artifact")

        async def stale_file_count_for_settings(settings: EffectiveAiSettings) -> int:
            return await self._stale_file_count_for_settings(settings)

        def promoted_effective_settings(
            settings: EffectiveAiSettings,
            setting_value: str,
        ) -> EffectiveAiSettings:
            return self._promoted_effective_settings(
                settings,
                setting_value=setting_value,
            )

        return await self.registry.promote_model_row(
            model_row,
            updated_by=updated_by,
            stale_file_count_for_settings=stale_file_count_for_settings,
            promoted_effective_settings=promoted_effective_settings,
        )

    async def get_worker_registry_model(
        self,
        model_id: str,
    ) -> ContentEnrichmentWorkerRegistryModel | None:
        """Return one ready registry model for worker-side inference loading."""
        model_row = await self._load_registry_model_row(model_id)
        if model_row is None or model_row.status != "ready":
            return None
        artifact_path = (
            model_row.artifact_path.strip() if model_row.artifact_path else ""
        )
        if not artifact_path:
            return None
        return ContentEnrichmentWorkerRegistryModel(
            id=model_row.id,
            target_kind=model_row.target_kind,
            training_method=model_row.training_method,
            base_model=model_row.base_model,
            target_name=model_row.target_name,
            config_fingerprint=model_row.config_fingerprint,
            artifact_path=artifact_path,
        )
