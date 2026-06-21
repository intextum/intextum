"""Service layer for runtime-overridable AI application settings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import config as app_config
from models.ai_settings import (
    AiSettingEntry,
    AiSettingsInputType,
    AiSettingsResponse,
    AiSettingsSection,
    EffectiveAiSettings,
)
from models.content.enrichment_catalog import (
    catalog_classes_to_runtime_labels,
    catalog_classes_to_runtime_schemas,
)
from models.sqlalchemy_models import AppSetting
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class AiSettingDefinition:
    """Metadata describing one admin-editable AI setting."""

    key: str
    attr_name: str
    section: AiSettingsSection
    label: str
    description: str
    input_type: AiSettingsInputType


AI_SETTING_DEFINITIONS: tuple[AiSettingDefinition, ...] = (
    AiSettingDefinition(
        key="chat_model",
        attr_name="CHAT_MODEL",
        section="chat",
        label="Chat Model",
        description="OpenAI-compatible model name used for LangGraph chat responses.",
        input_type="text",
    ),
    AiSettingDefinition(
        key="chat_system_prompt",
        attr_name="CHAT_SYSTEM_PROMPT",
        section="chat",
        label="Chat System Prompt",
        description="Base instruction shown to the chat model before any user messages.",
        input_type="textarea",
    ),
    AiSettingDefinition(
        key="chat_tool_prompt",
        attr_name="CHAT_TOOL_PROMPT",
        section="chat",
        label="Chat Tool Prompt",
        description="Tool/citation instructions appended to the system prompt.",
        input_type="textarea",
    ),
    AiSettingDefinition(
        key="chat_search_limit",
        attr_name="CHAT_SEARCH_LIMIT",
        section="chat",
        label="Search Result Limit",
        description="Maximum number of semantic search hits exposed to the chat model.",
        input_type="number",
    ),
    AiSettingDefinition(
        key="chat_document_max_chars",
        attr_name="CHAT_DOCUMENT_MAX_CHARS",
        section="chat",
        label="Document Character Limit",
        description="Maximum characters returned when reading a full document into chat.",
        input_type="number",
    ),
    AiSettingDefinition(
        key="picture_description_model",
        attr_name="PICTURE_DESCRIPTION_MODEL",
        section="image_description",
        label="Image Description Model",
        description="OpenAI-compatible VLM model name used for image descriptions.",
        input_type="text",
    ),
    AiSettingDefinition(
        key="picture_description_prompt",
        attr_name="PICTURE_DESCRIPTION_PROMPT",
        section="image_description",
        label="Image Description Prompt",
        description="Instruction sent with each worker-side image description request.",
        input_type="textarea",
    ),
    AiSettingDefinition(
        key="picture_description_max_tokens",
        attr_name="PICTURE_DESCRIPTION_MAX_TOKENS",
        section="image_description",
        label="Image Description Token Limit",
        description="Maximum generated tokens for each worker-side image description.",
        input_type="number",
    ),
    AiSettingDefinition(
        key="picture_description_enable_thinking",
        attr_name="PICTURE_DESCRIPTION_ENABLE_THINKING",
        section="image_description",
        label="Enable Image Description Thinking",
        description=(
            "Allow reasoning models to emit hidden thinking tokens before the visible"
            " image description. Off by default to keep the token budget for the"
            " description itself."
        ),
        input_type="boolean",
    ),
    AiSettingDefinition(
        key="document_classification_enabled",
        attr_name="DOCUMENT_CLASSIFICATION_ENABLED",
        section="content_enrichment",
        label="Enable Document Classification",
        description="Automatically classify processed documents.",
        input_type="boolean",
    ),
    AiSettingDefinition(
        key="document_classification_provider",
        attr_name="DOCUMENT_CLASSIFICATION_PROVIDER",
        section="content_enrichment",
        label="Document Classification Provider",
        description="Provider used for automatic document classification.",
        input_type="text",
    ),
    AiSettingDefinition(
        key="document_classification_model",
        attr_name="DOCUMENT_CLASSIFICATION_MODEL",
        section="content_enrichment",
        label="Document Classification Model",
        description="Model used for automatic document classification.",
        input_type="text",
    ),
    AiSettingDefinition(
        key="document_extraction_enabled",
        attr_name="DOCUMENT_EXTRACTION_ENABLED",
        section="content_enrichment",
        label="Enable Structured Extraction",
        description="Automatically extract structured data from processed documents.",
        input_type="boolean",
    ),
    AiSettingDefinition(
        key="document_extraction_model",
        attr_name="DOCUMENT_EXTRACTION_MODEL",
        section="content_enrichment",
        label="Legacy Structured Extraction Model",
        description=(
            "Legacy extraction model identifier retained for existing status and"
            " training metadata. Runtime extraction uses the LLM extraction model."
        ),
        input_type="text",
    ),
    AiSettingDefinition(
        key="document_extraction_llm_model",
        attr_name="DOCUMENT_EXTRACTION_LLM_MODEL",
        section="content_enrichment",
        label="LLM Structured Extraction Model",
        description="Model used for chat-based structured extraction.",
        input_type="text",
    ),
    AiSettingDefinition(
        key="document_extraction_llm_max_output_tokens",
        attr_name="DOCUMENT_EXTRACTION_LLM_MAX_OUTPUT_TOKENS",
        section="content_enrichment",
        label="LLM Structured Extraction Token Limit",
        description="Maximum generated tokens for complex structured extraction responses.",
        input_type="number",
    ),
    AiSettingDefinition(
        key="document_extraction_llm_enable_thinking",
        attr_name="DOCUMENT_EXTRACTION_LLM_ENABLE_THINKING",
        section="content_enrichment",
        label="Enable LLM Structured Extraction Thinking",
        description=(
            "Allow reasoning models to emit hidden thinking tokens before structured"
            " extraction output. Off by default so the token budget is spent on the"
            " extraction response, not on hidden reasoning."
        ),
        input_type="boolean",
    ),
    AiSettingDefinition(
        key="document_extraction_chunk_strategy",
        attr_name="DOCUMENT_EXTRACTION_CHUNK_STRATEGY",
        section="content_enrichment",
        label="Extraction Chunk Strategy",
        description="Whether chat extraction uses all chunks or selected relevant chunks.",
        input_type="text",
    ),
    AiSettingDefinition(
        key="document_extraction_chat_max_retries",
        attr_name="DOCUMENT_EXTRACTION_CHAT_MAX_RETRIES",
        section="content_enrichment",
        label="Chat Extraction Retries",
        description=(
            "How many times chat extraction retries when required fields are missing."
            " First retry sharpens the prompt; second retry also queries new chunks."
        ),
        input_type="number",
    ),
    AiSettingDefinition(
        key="document_extraction_chat_evidence_required",
        attr_name="DOCUMENT_EXTRACTION_CHAT_EVIDENCE_REQUIRED",
        section="content_enrichment",
        label="Chat Extraction Evidence Required",
        description=(
            "When enabled, chat-extracted values without a verifiable verbatim quote"
            " from the source are flagged as without evidence. When disabled,"
            " paraphrased values are also accepted."
        ),
        input_type="boolean",
    ),
    AiSettingDefinition(
        key="document_extraction_chat_full_text_threshold_chars",
        attr_name="DOCUMENT_EXTRACTION_CHAT_FULL_TEXT_THRESHOLD_CHARS",
        section="content_enrichment",
        label="Chat Extraction Full-Text Threshold",
        description=(
            "Maximum source text length (characters) at which chat extraction sends"
            " the full document in one call. Larger documents fall back to semantic"
            " chunk selection."
        ),
        input_type="number",
    ),
    AiSettingDefinition(
        key="document_extraction_schema_models",
        attr_name="DOCUMENT_EXTRACTION_SCHEMA_MODELS",
        section="content_enrichment",
        label="Schema-specific Extraction Models",
        description="Optional per-schema extraction model overrides keyed by schema name.",
        input_type="json",
    ),
    AiSettingDefinition(
        key="document_extraction_max_chars",
        attr_name="DOCUMENT_EXTRACTION_MAX_CHARS",
        section="content_enrichment",
        label="Structured Extraction Character Limit",
        description="Maximum normalized document text included in structured extraction.",
        input_type="number",
    ),
)

AI_SETTING_BY_KEY = {item.key: item for item in AI_SETTING_DEFINITIONS}
AI_SETTING_KEYS = tuple(item.key for item in AI_SETTING_DEFINITIONS)


def normalize_document_extraction_schema_models(value: Any) -> dict[str, str]:
    """Normalize one schema-name -> model-name mapping payload."""
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            continue
        key = raw_key.strip()
        model_name = raw_value.strip()
        if not key or not model_name:
            continue
        normalized[key] = model_name
    return normalized


def resolve_document_extraction_model_for_schema(
    settings: EffectiveAiSettings,
    schema_name: str | None,
) -> str:
    """Return the effective extraction-model marker for one configured schema."""
    normalized_schema_name = schema_name.strip() if isinstance(schema_name, str) else ""
    if normalized_schema_name:
        override = normalize_document_extraction_schema_models(
            settings.document_extraction_schema_models
        ).get(normalized_schema_name)
        if isinstance(override, str) and override.strip():
            return override.strip()
    return settings.document_extraction_llm_model


def expected_document_extraction_models_by_schema(
    settings: EffectiveAiSettings,
) -> dict[str, str]:
    """Return expected persisted extraction model markers by schema name."""
    return {
        schema.name: resolve_document_extraction_model_for_schema(settings, schema.name)
        for schema in settings.document_extraction_schemas
        if schema.name
    }


def resolve_document_extraction_provider_for_schema() -> str:
    """Return the expected provider metadata for one schema.

    The chat-style ``langgraph_extract`` provider handles every schema now;
    the helper is kept so persisted enrichment-state rows still get a stable
    provider marker that downstream views can compare against.
    """
    return "langgraph_extract"


def _stable_json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _json_list(values: list[Any]) -> list[Any]:
    return [_json_value(item) for item in values]


def document_classification_config_fingerprint(
    settings: EffectiveAiSettings,
) -> str:
    """Return a stable fingerprint for the effective classification configuration."""
    payload = {
        "enabled": settings.document_classification_enabled,
        "provider": settings.document_classification_provider,
        "model": settings.document_classification_model,
        "labels": _json_list(settings.document_classification_labels),
    }
    return _stable_json_hash(payload)


def document_extraction_config_fingerprint(
    settings: EffectiveAiSettings,
) -> str:
    """Return a stable fingerprint for the effective extraction configuration."""
    payload = {
        "enabled": settings.document_extraction_enabled,
        "model": settings.document_extraction_model,
        "llm_model": settings.document_extraction_llm_model,
        "llm_max_output_tokens": settings.document_extraction_llm_max_output_tokens,
        "chunk_strategy": settings.document_extraction_chunk_strategy,
        "max_chars": settings.document_extraction_max_chars,
        "schemas": _json_list(settings.document_extraction_schemas),
        "classification_fingerprint": document_classification_config_fingerprint(
            settings
        ),
    }
    return _stable_json_hash(payload)


class AiSettingsService:
    """Loads and mutates the AI settings that admins can override at runtime."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _admin_value(value: Any) -> Any:
        """Convert effective values into plain JSON-friendly admin payloads."""
        if isinstance(value, list):
            return _json_list(value)
        return value

    @staticmethod
    def _base_defaults() -> EffectiveAiSettings:
        """Return the deployment-configured default AI settings."""
        settings = app_config.get_settings()
        return EffectiveAiSettings.model_validate(
            {
                definition.key: getattr(settings, definition.attr_name)
                for definition in AI_SETTING_DEFINITIONS
            }
        )

    async def _load_override_rows(self) -> dict[str, AppSetting]:
        """Load persisted AI override rows keyed by lower-snake-case setting key."""
        result = await self.db.execute(
            select(AppSetting).where(AppSetting.key.in_(AI_SETTING_KEYS))
        )
        rows = result.scalars().all()
        return {row.key: row for row in rows if row.key in AI_SETTING_BY_KEY}

    async def get_effective_settings(self) -> EffectiveAiSettings:
        """Return effective AI settings after overlaying DB overrides on defaults."""
        defaults = self._base_defaults()
        overrides = await self._load_override_rows()
        data = defaults.model_dump()

        for key, row in overrides.items():
            data[key] = row.value_json

        data["document_extraction_schema_models"] = (
            normalize_document_extraction_schema_models(
                data.get("document_extraction_schema_models")
            )
        )
        from services.content.enrichment.catalog import ContentEnrichmentCatalogService

        catalog = await ContentEnrichmentCatalogService(self.db).get_effective_catalog()
        data["document_classification_labels"] = _json_list(
            catalog_classes_to_runtime_labels(catalog.document_classes)
        )
        data["document_extraction_schemas"] = _json_list(
            catalog_classes_to_runtime_schemas(catalog.document_classes)
        )

        return EffectiveAiSettings.model_validate(data)

    async def get_admin_response(self) -> AiSettingsResponse:
        """Return admin metadata plus effective/default values for UI editing."""
        defaults = self._base_defaults()
        overrides = await self._load_override_rows()
        effective = await self.get_effective_settings()

        items = [
            AiSettingEntry(
                key=definition.key,
                section=definition.section,
                label=definition.label,
                description=definition.description,
                input_type=definition.input_type,
                value=self._admin_value(getattr(effective, definition.key)),
                default_value=self._admin_value(getattr(defaults, definition.key)),
                overridden=definition.key in overrides,
            )
            for definition in AI_SETTING_DEFINITIONS
        ]
        return AiSettingsResponse(items=items)

    async def update_settings(
        self,
        updates: dict[str, Any],
        *,
        updated_by: str | None = None,
    ) -> AiSettingsResponse:
        """Persist one or more overrides, removing rows that match defaults."""
        defaults = self._base_defaults()
        existing = await self._load_override_rows()

        for key, value in updates.items():
            if key not in AI_SETTING_BY_KEY:
                continue

            default_value = getattr(defaults, key)
            row = existing.get(key)
            if value == default_value:
                if row is not None:
                    await self.db.delete(row)
                continue

            if row is None:
                row = AppSetting(
                    key=key,
                    value_json=value,
                    updated_by=updated_by,
                )
                self.db.add(row)
                existing[key] = row
                continue

            row.value_json = value
            row.updated_by = updated_by

        await self.db.commit()
        return await self.get_admin_response()

    async def reset_settings(self, keys: list[str] | None = None) -> AiSettingsResponse:
        """Delete one or more overrides so deployment defaults become effective again."""
        override_rows = await self._load_override_rows()
        keys_to_reset = keys or list(override_rows.keys())

        for key in keys_to_reset:
            row = override_rows.get(key)
            if row is not None:
                await self.db.delete(row)

        await self.db.commit()
        return await self.get_admin_response()
