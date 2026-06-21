"""Registry and settings helpers for content-enrichment training."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_settings import EffectiveAiSettings
from models.content.enrichment_training import (
    CreateContentEnrichmentFineTuneJobRequest,
    ContentEnrichmentModelPromotionResponse,
)
from models.sqlalchemy_models import (
    AppSetting,
    ContentEnrichmentFineTuneJob,
    ContentEnrichmentModelRegistry,
    IndexedContentItem,
    TaskQueue,
)
from services.ai_settings import (
    AiSettingsService,
    document_classification_config_fingerprint,
    document_extraction_config_fingerprint,
    expected_document_extraction_models_by_schema,
)
from services.content.stats import ContentStatsService
from .refs import (
    content_enrichment_registry_model_ref,
    parse_content_enrichment_registry_model_ref,
)


class ContentEnrichmentTrainingRegistry:
    """Registry row lookups and AI-settings calculations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def load_registry_model_row(
        self, model_id: str
    ) -> ContentEnrichmentModelRegistry | None:
        result = await self.db.execute(
            select(ContentEnrichmentModelRegistry).where(
                ContentEnrichmentModelRegistry.id == model_id
            )
        )
        return result.scalar_one_or_none()

    async def load_job_row(self, job_id: str) -> ContentEnrichmentFineTuneJob | None:
        result = await self.db.execute(
            select(ContentEnrichmentFineTuneJob).where(
                ContentEnrichmentFineTuneJob.id == job_id
            )
        )
        return result.scalar_one_or_none()

    async def load_queue_task_row(self, task_id: str | None) -> TaskQueue | None:
        if not isinstance(task_id, str) or not task_id.strip():
            return None
        result = await self.db.execute(
            select(TaskQueue).where(TaskQueue.id == task_id.strip())
        )
        return result.scalar_one_or_none()

    async def active_model_ids(self) -> set[str]:
        effective_settings = await AiSettingsService(self.db).get_effective_settings()
        active_model_ids = set(
            filter(
                None,
                (
                    parse_content_enrichment_registry_model_ref(
                        effective_settings.document_classification_model
                    ),
                ),
            )
        )
        return active_model_ids

    @staticmethod
    def promoted_effective_settings(
        settings: EffectiveAiSettings,
        *,
        setting_value: str,
    ) -> EffectiveAiSettings:
        return settings.model_copy(
            update={"document_classification_model": setting_value}
        )

    async def stale_file_count_for_settings(
        self,
        settings: EffectiveAiSettings,
    ) -> int:
        classification_fingerprint = document_classification_config_fingerprint(
            settings
        )
        extraction_fingerprint = document_extraction_config_fingerprint(settings)
        stmt = select(func.count(IndexedContentItem.content_item_id)).where(
            IndexedContentItem.is_dir.is_(False),
            IndexedContentItem.is_hidden.is_(False),
            ContentStatsService._stale_enrichment_expr(
                classification_enabled=settings.document_classification_enabled,
                extraction_enabled=settings.document_extraction_enabled,
                classification_fingerprint=classification_fingerprint,
                extraction_fingerprint=extraction_fingerprint,
                extraction_model=settings.document_extraction_model,
                extraction_schema_models=expected_document_extraction_models_by_schema(
                    settings
                ),
            ),
        )
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def resolved_training_base_model(
        self,
        request: CreateContentEnrichmentFineTuneJobRequest,
        settings: EffectiveAiSettings,
    ) -> str:
        explicit_base_model = request.base_model.strip() if request.base_model else None
        if explicit_base_model:
            return explicit_base_model

        configured_model = settings.document_classification_model
        registry_model_id = parse_content_enrichment_registry_model_ref(
            configured_model
        )
        if not registry_model_id:
            return configured_model

        registry_model = await self.load_registry_model_row(registry_model_id)
        if registry_model is not None and isinstance(registry_model.base_model, str):
            normalized_base_model = registry_model.base_model.strip()
            if normalized_base_model:
                return normalized_base_model
        return configured_model

    @staticmethod
    def config_fingerprint(
        settings: EffectiveAiSettings,
    ) -> str:
        return document_classification_config_fingerprint(settings)

    @staticmethod
    def config_snapshot(
        settings: EffectiveAiSettings,
    ) -> dict[str, Any]:
        return {
            "document_classification_enabled": settings.document_classification_enabled,
            "document_classification_provider": (
                settings.document_classification_provider
            ),
            "document_classification_model": settings.document_classification_model,
            "document_classification_labels": [
                item.model_dump(mode="json")
                for item in settings.document_classification_labels
            ],
        }

    async def promote_model_row(
        self,
        model_row: ContentEnrichmentModelRegistry,
        *,
        updated_by: str | None,
        stale_file_count_for_settings: Callable[[EffectiveAiSettings], Awaitable[int]],
        promoted_effective_settings: Callable[
            [EffectiveAiSettings, str], EffectiveAiSettings
        ],
    ) -> ContentEnrichmentModelPromotionResponse:
        effective_settings = await AiSettingsService(self.db).get_effective_settings()
        setting_value = content_enrichment_registry_model_ref(model_row.id)
        stale_file_count_before = await stale_file_count_for_settings(
            effective_settings
        )
        setting_key = "document_classification_model"

        setting_result = await self.db.execute(
            select(AppSetting).where(AppSetting.key == setting_key)
        )
        setting_row = setting_result.scalar_one_or_none()
        if setting_row is None:
            self.db.add(
                AppSetting(
                    key=setting_key,
                    value_json=setting_value,
                    updated_by=updated_by,
                )
            )
        else:
            setting_row.value_json = setting_value
            setting_row.updated_by = updated_by

        promoted_settings = promoted_effective_settings(
            effective_settings,
            setting_value,
        )
        stale_file_count_after = await stale_file_count_for_settings(promoted_settings)
        await self.db.commit()
        return ContentEnrichmentModelPromotionResponse(
            model_id=model_row.id,
            target_kind=model_row.target_kind,
            target_name=model_row.target_name,
            setting_key=setting_key,
            setting_value=setting_value,
            stale_file_count=stale_file_count_after,
            newly_stale_file_count=max(
                0, stale_file_count_after - stale_file_count_before
            ),
        )

    @staticmethod
    def validate_request(
        request: CreateContentEnrichmentFineTuneJobRequest,
        settings: EffectiveAiSettings,
    ) -> None:
        if request.target_name:
            raise ValueError(
                "Classification fine-tuning does not accept a target schema"
            )
        if not settings.document_classification_labels:
            raise ValueError("No document classification labels are configured")

    @staticmethod
    def validate_reviewed_example_count(
        reviewed_example_count: int,
    ) -> None:
        if reviewed_example_count > 0:
            return
        raise ValueError(
            "No reviewed classification examples are available for training"
        )
