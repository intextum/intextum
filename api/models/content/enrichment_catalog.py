"""API models for class-owned content enrichment settings."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from models.ai_settings import (
    DocumentClassificationLabel,
    DocumentClassificationLabelInput,
    DocumentExtractionField,
    DocumentExtractionScene,
    DocumentExtractionSchema,
)


def _catalog_identifier(kind: str, name: str) -> str:
    normalized = name.strip().lower()
    return uuid5(NAMESPACE_URL, f"intextum:{kind}:{normalized}").hex


class ContentEnrichmentClassExtractionSchemaInput(BaseModel):
    """Optional extraction schema owned by one document class."""

    id: str = Field(default="", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1_000)
    fields: list[DocumentExtractionField] = Field(default_factory=list)
    scenes: list[DocumentExtractionScene] = Field(default_factory=list)

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
            data["id"] = _catalog_identifier("schema", name)
        return data


class ContentEnrichmentClassExtractionSchema(
    ContentEnrichmentClassExtractionSchemaInput
):
    """Stored class-owned extraction schema with lifecycle version metadata."""

    version: int = Field(default=1, ge=1)


class ContentEnrichmentDocumentClassInput(DocumentClassificationLabelInput):
    """One document class plus its optional extraction schema."""

    extraction_schema: ContentEnrichmentClassExtractionSchemaInput | None = None


class ContentEnrichmentDocumentClass(DocumentClassificationLabel):
    """Stored document class plus optional extraction schema."""

    extraction_schema: ContentEnrichmentClassExtractionSchema | None = None


class ContentEnrichmentCatalogResponse(BaseModel):
    """Active class-owned content enrichment settings."""

    document_classes: list[ContentEnrichmentDocumentClass] = Field(default_factory=list)


class ContentEnrichmentCatalogUpdateRequest(BaseModel):
    """Replace the active class-owned content enrichment settings."""

    document_classes: list[ContentEnrichmentDocumentClassInput] = Field(
        default_factory=list
    )

    model_config = ConfigDict(extra="forbid")


class ContentEnrichmentFieldExampleCandidatesRequest(BaseModel):
    """Request to surface stored extractions as candidate field examples."""

    content_item_ids: list[str] = Field(default_factory=list, max_length=50)

    model_config = ConfigDict(extra="forbid")


class ContentEnrichmentFieldExampleCandidate(BaseModel):
    """One candidate example drawn from a stored extraction record."""

    content_item_id: str
    relative_path: str
    review_status: str | None = None
    text: str
    anchor_text: str
    value: Any
    page_numbers: list[int] = Field(default_factory=list)
    chunk_index: int | None = None


class ContentEnrichmentFieldExampleCandidatesResponse(BaseModel):
    """Candidate examples for one extraction field, deduped by value."""

    candidates: list[ContentEnrichmentFieldExampleCandidate] = Field(
        default_factory=list
    )


def catalog_classes_to_runtime_labels(
    document_classes: list[ContentEnrichmentDocumentClass],
) -> list[DocumentClassificationLabel]:
    """Flatten class-owned API objects into worker/runtime classification labels."""
    return [
        DocumentClassificationLabel(
            id=item.id,
            version=item.version,
            name=item.name,
            description=item.description,
            aliases=item.aliases,
        )
        for item in document_classes
    ]


def catalog_classes_to_runtime_schemas(
    document_classes: list[ContentEnrichmentDocumentClass],
) -> list[DocumentExtractionSchema]:
    """Flatten class-owned API objects into worker/runtime extraction schemas."""
    schemas: list[DocumentExtractionSchema] = []
    for item in document_classes:
        if item.extraction_schema is None:
            continue
        schemas.append(
            DocumentExtractionSchema(
                id=item.extraction_schema.id,
                version=item.extraction_schema.version,
                name=item.extraction_schema.name,
                document_class_id=item.id,
                document_class=item.name,
                description=item.extraction_schema.description,
                fields=item.extraction_schema.fields,
                scenes=item.extraction_schema.scenes,
            )
        )
    return schemas
