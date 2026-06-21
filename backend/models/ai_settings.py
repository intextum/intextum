"""Typed admin/runtime models for AI-related application settings."""

from __future__ import annotations

from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator


AiSettingsSection = Literal["chat", "image_description", "content_enrichment"]
AiSettingsInputType = Literal["text", "textarea", "number", "boolean", "json"]


def _catalog_identifier(kind: str, name: str) -> str:
    normalized = name.strip().lower()
    return uuid5(NAMESPACE_URL, f"dms:{kind}:{normalized}").hex


class DocumentClassificationLabelInput(BaseModel):
    """One admin-defined document class exposed to GLiNER2 classification."""

    id: str = Field(default="", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1_000)
    aliases: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _populate_id(cls, value: Any):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        identifier = data.get("id")
        name = data.get("name")
        if (
            (not isinstance(identifier, str) or not identifier.strip())
            and isinstance(name, str)
            and name.strip()
        ):
            data["id"] = _catalog_identifier("class", name)
        return data


class DocumentClassificationLabel(DocumentClassificationLabelInput):
    """Stored document class definition with lifecycle version metadata."""

    version: int = Field(default=1, ge=1)


DocumentExtractionScalarDtype = Literal[
    "str", "int", "float", "bool", "list", "date", "currency"
]
DocumentExtractionDtype = Literal[
    "str", "int", "float", "bool", "list", "date", "currency", "object_list"
]
DocumentExtractionChunkStrategy = Literal["full", "selected"]
DOCUMENT_EXTRACTION_LLM_MAX_OUTPUT_TOKENS_LIMIT = 128_000


class DocumentExtractionChildField(BaseModel):
    """One child field inside a repeating structured object."""

    name: str = Field(min_length=1, max_length=120)
    dtype: DocumentExtractionScalarDtype = "str"
    description: str = Field(min_length=1, max_length=1_000)
    required: bool = False

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocumentExtractionExample(BaseModel):
    """One few-shot example for a configured extraction field."""

    text: str = Field(min_length=1, max_length=20_000)
    value: Any = None
    extraction_text: str | None = Field(default=None, max_length=20_000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def _validate_extraction_text_in_text(self):
        if self.extraction_text is not None:
            anchor = self.extraction_text.strip()
            if not anchor:
                self.extraction_text = None
            elif anchor not in self.text:
                raise ValueError("extraction_text_must_be_substring_of_text")
        return self


class DocumentExtractionSceneExtraction(BaseModel):
    """One grounded row inside a shared multi-field example scene."""

    field: str = Field(min_length=1, max_length=120)
    extraction_text: str = Field(min_length=1, max_length=20_000)
    value: Any = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocumentExtractionScene(BaseModel):
    """One shared passage with multiple anchored extractions across fields."""

    text: str = Field(min_length=1, max_length=20_000)
    extractions: list[DocumentExtractionSceneExtraction] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def _validate_extraction_anchors_in_text(self):
        for extraction in self.extractions:
            anchor = extraction.extraction_text.strip()
            if not anchor or anchor not in self.text:
                raise ValueError("scene_extraction_anchor_must_be_substring_of_text")
        return self


class DocumentExtractionField(BaseModel):
    """One extracted field within a document extraction schema."""

    name: str = Field(min_length=1, max_length=120)
    dtype: DocumentExtractionDtype = "str"
    description: str = Field(min_length=1, max_length=1_000)
    required: bool = False
    fields: list[DocumentExtractionChildField] = Field(default_factory=list)
    examples: list[DocumentExtractionExample] = Field(default_factory=list)
    heading_aliases: list[str] = Field(default_factory=list, max_length=20)
    clustered_under_heading: bool = True

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def _validate_nested_fields(self):
        if self.dtype != "object_list" and self.fields:
            raise ValueError("nested_fields_only_supported_for_object_list")
        if self.dtype == "object_list" and not self.fields:
            raise ValueError("object_list_fields_required")
        return self


class DocumentExtractionSchemaInput(BaseModel):
    """One admin-defined structured extraction contract."""

    id: str = Field(default="", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    document_class_id: str = Field(default="", max_length=64)
    document_class: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1_000)
    fields: list[DocumentExtractionField] = Field(default_factory=list)
    scenes: list[DocumentExtractionScene] = Field(default_factory=list)
    section_boundary_terms: list[str] = Field(default_factory=list, max_length=40)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _populate_identifiers(cls, value: Any):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        identifier = data.get("id")
        name = data.get("name")
        if (
            (not isinstance(identifier, str) or not identifier.strip())
            and isinstance(name, str)
            and name.strip()
        ):
            data["id"] = _catalog_identifier("schema", name)
        return data

    @model_validator(mode="after")
    def _validate_class_reference(self):
        if not self.document_class_id and not self.document_class:
            raise ValueError("document_class_reference_required")
        return self

    @model_validator(mode="after")
    def _validate_scene_field_references(self):
        if not self.scenes:
            return self
        field_names = {field.name for field in self.fields}
        for scene in self.scenes:
            for extraction in scene.extractions:
                if extraction.field not in field_names:
                    raise ValueError("scene_extraction_field_unknown")
        return self


class DocumentExtractionSchema(DocumentExtractionSchemaInput):
    """Stored extraction schema definition with lifecycle version metadata."""

    version: int = Field(default=1, ge=1)


class EffectiveAiSettings(BaseModel):
    """Effective AI settings after applying DB overrides to base config."""

    chat_model: str = Field(min_length=1, max_length=255)
    chat_system_prompt: str = Field(min_length=1, max_length=20_000)
    chat_tool_prompt: str = Field(min_length=1, max_length=20_000)
    chat_search_limit: int = Field(ge=1, le=50)
    chat_document_max_chars: int = Field(ge=1_000, le=200_000)
    picture_description_model: str = Field(min_length=1, max_length=255)
    picture_description_prompt: str = Field(min_length=1, max_length=20_000)
    picture_description_max_tokens: int = Field(default=512, ge=32, le=2048)
    picture_description_enable_thinking: bool = False
    document_classification_enabled: bool = False
    document_classification_provider: str = Field(
        default="gliner2", min_length=1, max_length=64
    )
    document_classification_model: str = Field(
        default="fastino/gliner2-multi-v1", min_length=1, max_length=255
    )
    document_classification_labels: list[DocumentClassificationLabel] = Field(
        default_factory=list
    )
    document_extraction_enabled: bool = False
    document_extraction_model: str = Field(
        default="fastino/gliner2-multi-v1", min_length=1, max_length=255
    )
    document_extraction_llm_model: str = Field(
        default="qwen3-vl:8b", min_length=1, max_length=255
    )
    document_extraction_llm_max_output_tokens: int = Field(
        default=16_384, ge=128, le=DOCUMENT_EXTRACTION_LLM_MAX_OUTPUT_TOKENS_LIMIT
    )
    document_extraction_llm_enable_thinking: bool = False
    document_extraction_chunk_strategy: DocumentExtractionChunkStrategy = "full"
    document_extraction_chat_max_retries: int = Field(default=2, ge=0, le=5)
    document_extraction_chat_evidence_required: bool = True
    document_extraction_chat_full_text_threshold_chars: int = Field(
        default=20_000, ge=1_000, le=100_000
    )
    document_extraction_schema_models: dict[str, str] = Field(default_factory=dict)
    document_extraction_schemas: list[DocumentExtractionSchema] = Field(
        default_factory=list
    )
    document_extraction_max_chars: int = Field(default=12_000, ge=500, le=100_000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def _validate_single_schema_per_class(self):
        seen_class_ids: set[str] = set()
        for schema in self.document_extraction_schemas:
            class_key = schema.document_class_id.strip().lower()
            if not class_key:
                class_key = schema.document_class.strip().lower()
            if not class_key:
                continue
            if class_key in seen_class_ids:
                raise ValueError("duplicate_extraction_schema_document_class")
            seen_class_ids.add(class_key)
        return self


class AiSettingEntry(BaseModel):
    """One admin-editable AI setting with metadata and effective state."""

    key: str
    section: AiSettingsSection
    label: str
    description: str
    input_type: AiSettingsInputType
    value: str | int | bool | list[dict[str, Any]] | dict[str, str]
    default_value: str | int | bool | list[dict[str, Any]] | dict[str, str]
    overridden: bool


class AiSettingsResponse(BaseModel):
    """Admin response payload for editable AI settings."""

    items: list[AiSettingEntry]


class AiSettingsUpdateRequest(BaseModel):
    """Patch payload for updating one or more AI settings."""

    chat_model: str | None = Field(default=None, min_length=1, max_length=255)
    chat_system_prompt: str | None = Field(
        default=None, min_length=1, max_length=20_000
    )
    chat_tool_prompt: str | None = Field(default=None, min_length=1, max_length=20_000)
    chat_search_limit: int | None = Field(default=None, ge=1, le=50)
    chat_document_max_chars: int | None = Field(default=None, ge=1_000, le=200_000)
    picture_description_model: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    picture_description_prompt: str | None = Field(
        default=None, min_length=1, max_length=20_000
    )
    picture_description_max_tokens: int | None = Field(default=None, ge=32, le=2048)
    picture_description_enable_thinking: bool | None = None
    document_classification_enabled: bool | None = None
    document_classification_provider: str | None = Field(
        default=None, min_length=1, max_length=64
    )
    document_classification_model: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    document_extraction_enabled: bool | None = None
    document_extraction_model: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    document_extraction_llm_model: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    document_extraction_llm_max_output_tokens: int | None = Field(
        default=None, ge=128, le=DOCUMENT_EXTRACTION_LLM_MAX_OUTPUT_TOKENS_LIMIT
    )
    document_extraction_llm_enable_thinking: bool | None = None
    document_extraction_chunk_strategy: DocumentExtractionChunkStrategy | None = None
    document_extraction_chat_max_retries: int | None = Field(default=None, ge=0, le=5)
    document_extraction_chat_evidence_required: bool | None = None
    document_extraction_chat_full_text_threshold_chars: int | None = Field(
        default=None, ge=1_000, le=100_000
    )
    document_extraction_schema_models: dict[str, str] | None = None
    document_extraction_max_chars: int | None = Field(default=None, ge=500, le=100_000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResetAiSettingsRequest(BaseModel):
    """Request payload for resetting AI settings to deployment defaults."""

    keys: list[str] | None = None

    model_config = ConfigDict(extra="forbid")
