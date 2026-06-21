"""Persistence layer for active class-owned content enrichment settings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config as app_config
from models.ai_settings import DocumentClassificationLabel, DocumentExtractionSchema
from models.content.enrichment_catalog import (
    ContentEnrichmentCatalogResponse,
    ContentEnrichmentDocumentClass,
    ContentEnrichmentDocumentClassInput,
    ContentEnrichmentClassExtractionSchema,
)
from models.sqlalchemy_models import (
    DocumentClassCatalogEntry,
    ExtractionSchemaCatalogEntry,
)


def _normalized_class_payload(entry: ContentEnrichmentDocumentClassInput) -> dict:
    return {
        "id": entry.id,
        "name": entry.name,
        "description": entry.description,
        "aliases": list(entry.aliases),
    }


def _json_list(values: list[Any]) -> list[Any]:
    return [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        for item in values
    ]


def _normalized_schema_payload(schema) -> dict:
    return {
        "id": schema.id,
        "name": schema.name,
        "description": schema.description,
        "fields": _json_list(schema.fields),
        "scenes": _json_list(getattr(schema, "scenes", [])),
    }


def _normalized_key(value: str) -> str:
    return value.strip().lower()


def _schema_from_row(
    row: ExtractionSchemaCatalogEntry,
) -> ContentEnrichmentClassExtractionSchema:
    return ContentEnrichmentClassExtractionSchema(
        id=row.id,
        name=row.name,
        version=max(1, int(row.version or 1)),
        description=row.description or "",
        fields=list(row.fields_json or []),
        scenes=list(row.scenes_json or []),
    )


def _validate_unique_catalog_entries(
    document_classes: list[ContentEnrichmentDocumentClassInput],
) -> None:
    class_ids: set[str] = set()
    class_names: set[str] = set()
    schema_ids: set[str] = set()
    schema_names: set[str] = set()

    for entry in document_classes:
        normalized_class_id = _normalized_key(entry.id)
        if normalized_class_id in class_ids:
            raise ValueError("Duplicate document class id")
        class_ids.add(normalized_class_id)

        normalized_class_name = _normalized_key(entry.name)
        if normalized_class_name in class_names:
            raise ValueError("Duplicate document class name")
        class_names.add(normalized_class_name)

        if entry.extraction_schema is None:
            continue
        normalized_schema_id = _normalized_key(entry.extraction_schema.id)
        if normalized_schema_id in schema_ids:
            raise ValueError("Duplicate extraction schema id")
        schema_ids.add(normalized_schema_id)

        normalized_schema_name = _normalized_key(entry.extraction_schema.name)
        if normalized_schema_name in schema_names:
            raise ValueError("Duplicate extraction schema name")
        schema_names.add(normalized_schema_name)


class ContentEnrichmentCatalogService:
    """Load and persist active document classes and their optional extraction schema."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _runtime_to_class_owned(
        *,
        classes: list[DocumentClassificationLabel],
        schemas: list[DocumentExtractionSchema],
    ) -> list[ContentEnrichmentDocumentClass]:
        schema_by_class_id = {
            schema.document_class_id: schema
            for schema in schemas
            if schema.document_class_id
        }
        schema_by_class_name = {
            schema.document_class.strip().lower(): schema
            for schema in schemas
            if schema.document_class.strip()
        }
        document_classes: list[ContentEnrichmentDocumentClass] = []
        for item in classes:
            schema = schema_by_class_id.get(item.id) or schema_by_class_name.get(
                item.name.strip().lower()
            )
            extraction_schema = (
                ContentEnrichmentClassExtractionSchema(
                    id=schema.id,
                    version=schema.version,
                    name=schema.name,
                    description=schema.description,
                    fields=schema.fields,
                    scenes=schema.scenes,
                )
                if schema is not None
                else None
            )
            document_classes.append(
                ContentEnrichmentDocumentClass(
                    id=item.id,
                    version=item.version,
                    name=item.name,
                    description=item.description,
                    aliases=item.aliases,
                    extraction_schema=extraction_schema,
                )
            )
        return document_classes

    @staticmethod
    def default_catalog() -> ContentEnrichmentCatalogResponse:
        """Return deployment-configured defaults as class-owned settings."""
        settings = app_config.get_settings()
        classes = [
            item
            if isinstance(item, DocumentClassificationLabel)
            else DocumentClassificationLabel.model_validate(item)
            for item in settings.DOCUMENT_CLASSIFICATION_LABELS
        ]
        schemas = [
            item
            if isinstance(item, DocumentExtractionSchema)
            else DocumentExtractionSchema.model_validate(item)
            for item in settings.DOCUMENT_EXTRACTION_SCHEMAS
        ]
        return ContentEnrichmentCatalogResponse(
            document_classes=ContentEnrichmentCatalogService._runtime_to_class_owned(
                classes=classes,
                schemas=schemas,
            )
        )

    async def _load_class_rows(self) -> list[DocumentClassCatalogEntry]:
        return (
            (
                await self.db.execute(
                    select(DocumentClassCatalogEntry).order_by(
                        DocumentClassCatalogEntry.name
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _load_schema_rows(self) -> list[ExtractionSchemaCatalogEntry]:
        return (
            (
                await self.db.execute(
                    select(ExtractionSchemaCatalogEntry).order_by(
                        ExtractionSchemaCatalogEntry.name
                    )
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _rows_to_document_classes(
        class_rows: list[DocumentClassCatalogEntry],
        schema_rows: list[ExtractionSchemaCatalogEntry],
    ) -> list[ContentEnrichmentDocumentClass]:
        schema_by_class_id = {row.document_class_id: row for row in schema_rows}
        document_classes: list[ContentEnrichmentDocumentClass] = []
        for row in class_rows:
            schema_row = schema_by_class_id.get(row.id)
            extraction_schema = (
                _schema_from_row(schema_row) if schema_row is not None else None
            )
            document_classes.append(
                ContentEnrichmentDocumentClass(
                    id=row.id,
                    name=row.name,
                    version=max(1, int(row.version or 1)),
                    description=row.description or "",
                    aliases=list(row.aliases_json or []),
                    extraction_schema=extraction_schema,
                )
            )
        return document_classes

    async def get_catalog(self) -> ContentEnrichmentCatalogResponse:
        """Return the active class-owned enrichment settings."""
        return ContentEnrichmentCatalogResponse(
            document_classes=self._rows_to_document_classes(
                await self._load_class_rows(),
                await self._load_schema_rows(),
            )
        )

    async def get_effective_catalog(self) -> ContentEnrichmentCatalogResponse:
        """Return the active worker-facing catalog."""
        return await self.get_catalog()

    async def replace_catalog(
        self,
        *,
        document_classes: list[ContentEnrichmentDocumentClassInput],
    ) -> ContentEnrichmentCatalogResponse:
        """Replace the active class-owned enrichment settings in one transaction."""
        _validate_unique_catalog_entries(document_classes)

        existing_classes = {
            row.id: row
            for row in (await self.db.execute(select(DocumentClassCatalogEntry)))
            .scalars()
            .all()
        }
        existing_schemas = {
            row.id: row
            for row in (await self.db.execute(select(ExtractionSchemaCatalogEntry)))
            .scalars()
            .all()
        }

        incoming_class_ids = {entry.id for entry in document_classes}
        incoming_schema_ids = {
            entry.extraction_schema.id
            for entry in document_classes
            if entry.extraction_schema is not None
        }

        for schema_id, row in existing_schemas.items():
            if schema_id not in incoming_schema_ids:
                await self.db.delete(row)
        for class_id, row in existing_classes.items():
            if class_id not in incoming_class_ids:
                await self.db.delete(row)

        for entry in document_classes:
            row = existing_classes.get(entry.id)
            normalized_payload = _normalized_class_payload(entry)
            if row is None:
                row = DocumentClassCatalogEntry(id=entry.id, name=entry.name, version=1)
                self.db.add(row)
            else:
                current_payload = _normalized_class_payload(
                    ContentEnrichmentDocumentClassInput(
                        id=row.id,
                        name=row.name,
                        description=row.description or "",
                        aliases=list(row.aliases_json or []),
                    )
                )
                if current_payload != normalized_payload:
                    row.version = max(1, int(row.version or 1)) + 1
            row.name = entry.name
            row.description = entry.description
            row.aliases_json = [alias for alias in entry.aliases]

            schema = entry.extraction_schema
            if schema is None:
                continue
            schema_row = existing_schemas.get(schema.id)
            normalized_schema = _normalized_schema_payload(schema)
            if schema_row is None:
                schema_row = ExtractionSchemaCatalogEntry(
                    id=schema.id,
                    name=schema.name,
                    version=1,
                )
                self.db.add(schema_row)
            else:
                current_schema = _schema_from_row(schema_row)
                if _normalized_schema_payload(current_schema) != normalized_schema:
                    schema_row.version = max(1, int(schema_row.version or 1)) + 1
            schema_row.name = schema.name
            schema_row.document_class_id = entry.id
            schema_row.description = schema.description
            schema_row.fields_json = _json_list(schema.fields)
            schema_row.scenes_json = _json_list(schema.scenes)

        await self.db.commit()
        return await self.get_catalog()

    async def reset_catalog(self) -> ContentEnrichmentCatalogResponse:
        """Reset the active catalog to deployment-configured defaults."""
        defaults = self.default_catalog()
        return await self.replace_catalog(
            document_classes=[
                ContentEnrichmentDocumentClassInput.model_validate(
                    item.model_dump(mode="json")
                )
                for item in defaults.document_classes
            ]
        )
