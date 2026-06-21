"""Tests for active class-owned content enrichment catalog persistence."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.content.enrichment_catalog import (
    ContentEnrichmentCatalogResponse,
    ContentEnrichmentDocumentClass,
    ContentEnrichmentDocumentClassInput,
)
from models.sqlalchemy_models import (
    DocumentClassCatalogEntry,
    ExtractionSchemaCatalogEntry,
)
from services.content.enrichment import ContentEnrichmentCatalogService


def _result_with_rows(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    return result


def _class_payload(**overrides) -> ContentEnrichmentDocumentClassInput:
    payload = {
        "id": "invoice",
        "name": "Invoice",
        "description": "Billing document",
        "aliases": ["Rechnung"],
        "extraction_schema": {
            "id": "invoice_fields",
            "name": "invoice_fields",
            "description": "Extract invoice fields",
            "fields": [
                {
                    "name": "invoice_number",
                    "dtype": "str",
                    "description": "Invoice number",
                    "required": True,
                }
            ],
        },
    }
    payload.update(overrides)
    return ContentEnrichmentDocumentClassInput.model_validate(payload)


@pytest.mark.asyncio
async def test_get_catalog_returns_active_class_owned_shape():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result_with_rows(
                [
                    DocumentClassCatalogEntry(
                        id="invoice",
                        name="Invoice",
                        version=2,
                        description="Billing document",
                        aliases_json=["Rechnung"],
                    )
                ]
            ),
            _result_with_rows(
                [
                    ExtractionSchemaCatalogEntry(
                        id="invoice_fields",
                        document_class_id="invoice",
                        name="invoice_fields",
                        version=3,
                        description="Extract invoice fields",
                        fields_json=[
                            {
                                "name": "invoice_number",
                                "dtype": "str",
                                "description": "Invoice number",
                                "required": True,
                            }
                        ],
                        scenes_json=[
                            {
                                "text": "Invoice number INV-1",
                                "extractions": [
                                    {
                                        "field": "invoice_number",
                                        "extraction_text": "INV-1",
                                        "value": "INV-1",
                                    }
                                ],
                            }
                        ],
                    )
                ]
            ),
        ]
    )

    result = await ContentEnrichmentCatalogService(db).get_catalog()

    assert result.document_classes[0].name == "Invoice"
    assert result.document_classes[0].version == 2
    assert result.document_classes[0].extraction_schema is not None
    assert result.document_classes[0].extraction_schema.name == "invoice_fields"
    assert result.document_classes[0].extraction_schema.version == 3
    assert result.document_classes[0].extraction_schema.scenes[0].text == (
        "Invoice number INV-1"
    )


@pytest.mark.asyncio
async def test_replace_catalog_upserts_document_class_with_nested_schema():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result_with_rows([]), _result_with_rows([])])
    db.add = MagicMock()
    expected = ContentEnrichmentCatalogResponse(
        document_classes=[
            ContentEnrichmentDocumentClass.model_validate(
                _class_payload().model_dump(mode="json")
            )
        ]
    )

    with patch.object(
        ContentEnrichmentCatalogService,
        "get_catalog",
        new=AsyncMock(return_value=expected),
    ):
        result = await ContentEnrichmentCatalogService(db).replace_catalog(
            document_classes=[_class_payload()],
        )

    assert result == expected
    assert db.add.call_count == 2
    schema_row = db.add.call_args_list[1].args[0]
    assert schema_row.scenes_json == []
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_replace_catalog_increments_versions_only_when_content_changes():
    existing_class = DocumentClassCatalogEntry(
        id="invoice",
        name="Invoice",
        version=4,
        description="Billing document",
        aliases_json=["Rechnung"],
    )
    existing_schema = ExtractionSchemaCatalogEntry(
        id="invoice_fields",
        document_class_id="invoice",
        name="invoice_fields",
        version=7,
        description="Extract invoice fields",
        fields_json=[
            {
                "name": "invoice_number",
                "dtype": "str",
                "description": "Invoice number",
                "required": True,
            }
        ],
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result_with_rows([existing_class]),
            _result_with_rows([existing_schema]),
        ]
    )

    with patch.object(
        ContentEnrichmentCatalogService,
        "get_catalog",
        new=AsyncMock(return_value=ContentEnrichmentCatalogResponse()),
    ):
        await ContentEnrichmentCatalogService(db).replace_catalog(
            document_classes=[_class_payload(description="Updated billing document")],
        )

    assert existing_class.version == 5
    assert existing_schema.version == 7


@pytest.mark.asyncio
async def test_replace_catalog_increments_schema_version_when_scenes_change():
    existing_class = DocumentClassCatalogEntry(
        id="invoice",
        name="Invoice",
        version=4,
        description="Billing document",
        aliases_json=["Rechnung"],
    )
    existing_schema = ExtractionSchemaCatalogEntry(
        id="invoice_fields",
        document_class_id="invoice",
        name="invoice_fields",
        version=7,
        description="Extract invoice fields",
        fields_json=[
            {
                "name": "invoice_number",
                "dtype": "str",
                "description": "Invoice number",
                "required": True,
            }
        ],
        scenes_json=[],
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result_with_rows([existing_class]),
            _result_with_rows([existing_schema]),
        ]
    )

    extraction_schema = _class_payload().extraction_schema.model_dump(mode="json")
    extraction_schema["scenes"] = [
        {
            "text": "Invoice number INV-1",
            "extractions": [
                {
                    "field": "invoice_number",
                    "extraction_text": "INV-1",
                    "value": "INV-1",
                }
            ],
        }
    ]

    with patch.object(
        ContentEnrichmentCatalogService,
        "get_catalog",
        new=AsyncMock(return_value=ContentEnrichmentCatalogResponse()),
    ):
        await ContentEnrichmentCatalogService(db).replace_catalog(
            document_classes=[_class_payload(extraction_schema=extraction_schema)],
        )

    assert existing_class.version == 4
    assert existing_schema.version == 8
    assert existing_schema.scenes_json == extraction_schema["scenes"]


@pytest.mark.asyncio
async def test_replace_catalog_removing_extraction_deletes_schema():
    existing_class = DocumentClassCatalogEntry(
        id="invoice",
        name="Invoice",
        version=1,
        description="Billing document",
        aliases_json=[],
    )
    existing_schema = ExtractionSchemaCatalogEntry(
        id="invoice_fields",
        document_class_id="invoice",
        name="invoice_fields",
        version=1,
        description="Extract invoice fields",
        fields_json=[],
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result_with_rows([existing_class]),
            _result_with_rows([existing_schema]),
        ]
    )

    with patch.object(
        ContentEnrichmentCatalogService,
        "get_catalog",
        new=AsyncMock(return_value=ContentEnrichmentCatalogResponse()),
    ):
        await ContentEnrichmentCatalogService(db).replace_catalog(
            document_classes=[_class_payload(extraction_schema=None)],
        )

    db.delete.assert_awaited_once_with(existing_schema)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_replace_catalog_rejects_duplicate_class_and_schema_names():
    db = AsyncMock()
    duplicate_class = _class_payload(id="invoice_copy")

    with pytest.raises(ValueError, match="Duplicate document class name"):
        await ContentEnrichmentCatalogService(db).replace_catalog(
            document_classes=[_class_payload(), duplicate_class],
        )

    db.commit.assert_not_awaited()

    with pytest.raises(ValueError, match="Duplicate extraction schema name"):
        await ContentEnrichmentCatalogService(db).replace_catalog(
            document_classes=[
                _class_payload(),
                _class_payload(
                    id="receipt",
                    name="Receipt",
                    extraction_schema={
                        "id": "receipt_fields",
                        "name": "invoice_fields",
                        "description": "Extract receipt fields",
                        "fields": [],
                    },
                ),
            ],
        )

    db.commit.assert_not_awaited()
