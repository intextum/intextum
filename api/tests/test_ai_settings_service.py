"""Tests for runtime-overridable AI settings service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from models.ai_settings import (
    AiSettingsResponse,
    DocumentClassificationLabel,
    EffectiveAiSettings,
)
from models.sqlalchemy_models import AppSetting
from config import Settings
from services.ai_settings import (
    AiSettingsService,
    document_classification_config_fingerprint,
    document_extraction_config_fingerprint,
    resolve_document_extraction_model_for_schema,
)
from models.content.enrichment_catalog import ContentEnrichmentCatalogResponse


def _db_with_rows(*rows: AppSetting) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    db.execute.return_value = result
    db.add = MagicMock()
    return db


def test_resolve_document_extraction_model_for_schema_uses_override_or_llm_model(
    mock_get_settings,
):
    base = AiSettingsService._base_defaults().model_dump(mode="json")
    settings = EffectiveAiSettings.model_validate(
        {
            **base,
            "document_extraction_llm_model": "llm-default",
            "document_extraction_schema_models": {"override_fields": "llm-override"},
            "document_extraction_schemas": [
                {
                    "name": "override_fields",
                    "document_class": "Invoice",
                    "fields": [
                        {
                            "name": "invoice_number",
                            "dtype": "str",
                            "description": "Invoice number",
                            "examples": [
                                {
                                    "text": "Invoice 1",
                                    "value": "1",
                                }
                            ],
                        }
                    ],
                },
                {
                    "name": "default_fields",
                    "document_class": "Task",
                    "fields": [
                        {
                            "name": "tasks",
                            "dtype": "object_list",
                            "description": "Tasks",
                            "fields": [
                                {
                                    "name": "title",
                                    "dtype": "str",
                                    "description": "Task title",
                                }
                            ],
                            "examples": [
                                {
                                    "text": "Submit the report.",
                                    "value": {"title": "Submit the report"},
                                }
                            ],
                        }
                    ],
                },
            ],
        }
    )

    assert (
        resolve_document_extraction_model_for_schema(settings, "override_fields")
        == "llm-override"
    )
    assert (
        resolve_document_extraction_model_for_schema(settings, "default_fields")
        == "llm-default"
    )


@pytest.mark.asyncio
async def test_get_effective_settings_overlays_database_overrides(mock_get_settings):
    db = _db_with_rows(
        AppSetting(key="chat_model", value_json="admin-chat-model"),
        AppSetting(key="chat_search_limit", value_json=7),
        AppSetting(
            key="picture_description_prompt",
            value_json="Describe this image for archival search.",
        ),
    )

    with patch(
        "services.content.enrichment.catalog.ContentEnrichmentCatalogService.get_effective_catalog",
        new=AsyncMock(
            return_value=ContentEnrichmentCatalogResponse(document_classes=[])
        ),
    ):
        settings = await AiSettingsService(db).get_effective_settings()

    assert settings.chat_model == "admin-chat-model"
    assert settings.chat_search_limit == 7
    assert (
        settings.picture_description_prompt
        == "Describe this image for archival search."
    )
    assert settings.chat_tool_prompt == mock_get_settings.CHAT_TOOL_PROMPT


@pytest.mark.asyncio
async def test_update_settings_upserts_rows_and_removes_default_matches(
    mock_get_settings,
):
    existing_row = AppSetting(
        key="chat_search_limit", value_json=4, updated_by="old-admin"
    )
    db = _db_with_rows(existing_row)
    response = AiSettingsResponse(items=[])

    with patch.object(
        AiSettingsService,
        "get_admin_response",
        new=AsyncMock(return_value=response),
    ):
        result = await AiSettingsService(db).update_settings(
            {
                "chat_model": "team-chat-model",
                "chat_search_limit": mock_get_settings.CHAT_SEARCH_LIMIT,
            },
            updated_by="admin-user",
        )

    assert result is response
    db.add.assert_called_once()
    added_row = db.add.call_args.args[0]
    assert isinstance(added_row, AppSetting)
    assert added_row.key == "chat_model"
    assert added_row.value_json == "team-chat-model"
    assert added_row.updated_by == "admin-user"
    db.delete.assert_awaited_once_with(existing_row)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_settings_deletes_selected_overrides_only():
    chat_model_row = AppSetting(key="chat_model", value_json="custom")
    vlm_row = AppSetting(key="picture_description_model", value_json="vlm-custom")
    db = _db_with_rows(chat_model_row, vlm_row)
    response = AiSettingsResponse(items=[])

    with patch.object(
        AiSettingsService,
        "get_admin_response",
        new=AsyncMock(return_value=response),
    ):
        result = await AiSettingsService(db).reset_settings(
            keys=["picture_description_model"]
        )

    assert result is response
    db.delete.assert_awaited_once_with(vlm_row)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_settings_persists_content_enrichment_runtime_values():
    db = _db_with_rows()
    response = AiSettingsResponse(items=[])

    with patch.object(
        AiSettingsService,
        "get_admin_response",
        new=AsyncMock(return_value=response),
    ):
        result = await AiSettingsService(db).update_settings(
            {
                "document_classification_enabled": True,
                "document_extraction_model": "fastino/gliner2-multi-v2",
                "document_extraction_schema_models": {
                    "invoice_fields": "registry:model-2"
                },
                "document_extraction_chunk_strategy": "selected",
            },
            updated_by="admin-user",
        )

    assert result is response
    assert db.add.call_count == 4
    added_rows = {call.args[0].key: call.args[0] for call in db.add.call_args_list}
    assert added_rows["document_classification_enabled"].value_json is True
    assert (
        added_rows["document_extraction_model"].value_json == "fastino/gliner2-multi-v2"
    )
    assert added_rows["document_extraction_schema_models"].value_json == {
        "invoice_fields": "registry:model-2"
    }
    assert added_rows["document_extraction_chunk_strategy"].value_json == "selected"


def test_effective_settings_rejects_invalid_extraction_chunk_strategy(
    mock_get_settings,
):
    base = AiSettingsService._base_defaults().model_dump(mode="json")

    with pytest.raises(ValidationError):
        EffectiveAiSettings.model_validate(
            {**base, "document_extraction_chunk_strategy": "everything"}
        )


def test_backend_settings_rejects_invalid_extraction_chunk_strategy():
    with pytest.raises(ValidationError):
        Settings(DOCUMENT_EXTRACTION_CHUNK_STRATEGY="everything")


@pytest.mark.asyncio
async def test_get_effective_settings_uses_content_enrichment_catalog():
    db = _db_with_rows()

    with patch(
        "services.content.enrichment.catalog.ContentEnrichmentCatalogService.get_effective_catalog",
        new=AsyncMock(
            return_value=ContentEnrichmentCatalogResponse(
                document_classes=[
                    {
                        "name": "Invoice",
                        "version": 2,
                        "description": "Billing document",
                        "aliases": ["Rechnung"],
                        "extraction_schema": {
                            "name": "invoice_fields",
                            "version": 4,
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
                    },
                    {
                        "name": "Permit",
                        "version": 1,
                        "description": "Permit document",
                        "aliases": [],
                        "extraction_schema": None,
                    },
                ],
            )
        ),
    ):
        settings = await AiSettingsService(db).get_effective_settings()

    assert settings.document_classification_labels[0].name == "Invoice"
    assert settings.document_classification_labels[0].version == 2
    assert settings.document_classification_labels[1].name == "Permit"
    assert len(settings.document_extraction_schemas) == 1
    assert settings.document_extraction_schemas[0].name == "invoice_fields"
    assert settings.document_extraction_schemas[0].version == 4
    assert settings.document_extraction_schemas[0].document_class == "Invoice"


@pytest.mark.asyncio
async def test_get_effective_settings_omits_extraction_for_class_without_schema():
    db = _db_with_rows()

    with patch(
        "services.content.enrichment.catalog.ContentEnrichmentCatalogService.get_effective_catalog",
        new=AsyncMock(
            return_value=ContentEnrichmentCatalogResponse(
                document_classes=[
                    {
                        "name": "Invoice",
                        "description": "Billing document",
                        "aliases": [],
                        "extraction_schema": None,
                    },
                    {
                        "name": "Receipt",
                        "description": "Receipt document",
                        "aliases": [],
                        "extraction_schema": {
                            "name": "receipt_fields",
                            "description": "Extract receipt fields",
                            "fields": [
                                {
                                    "name": "total",
                                    "dtype": "str",
                                    "description": "Receipt total",
                                    "required": True,
                                }
                            ],
                        },
                    },
                ],
            )
        ),
    ):
        settings = await AiSettingsService(db).get_effective_settings()

    assert [item.name for item in settings.document_classification_labels] == [
        "Invoice",
        "Receipt",
    ]
    assert [item.name for item in settings.document_extraction_schemas] == [
        "receipt_fields"
    ]


def test_content_enrichment_fingerprints_change_when_settings_change(mock_get_settings):
    settings = AiSettingsService._base_defaults()

    base_classification = document_classification_config_fingerprint(settings)
    base_extraction = document_extraction_config_fingerprint(settings)

    changed = settings.model_copy(
        update={
            "document_classification_enabled": True,
            "document_classification_labels": [
                {
                    "name": "Invoice",
                    "description": "Billing document",
                    "aliases": ["Rechnung"],
                }
            ],
            "document_extraction_enabled": True,
            "document_extraction_schemas": [
                {
                    "name": "invoice_fields",
                    "document_class": "Invoice",
                    "description": "Extract invoice data",
                    "fields": [
                        {
                            "name": "invoice_number",
                            "dtype": "str",
                            "description": "Invoice number",
                            "required": True,
                        }
                    ],
                }
            ],
        }
    )

    assert document_classification_config_fingerprint(changed) != base_classification
    assert document_extraction_config_fingerprint(changed) != base_extraction


def test_admin_value_serializes_mixed_model_lists():
    label = DocumentClassificationLabel(
        name="Invoice",
        description="Billing document",
        aliases=["Rechnung"],
    )
    payload = AiSettingsService._admin_value(
        [
            label,
            {"name": "Permit", "description": "Permit document", "aliases": []},
        ]
    )

    assert payload == [
        label.model_dump(mode="json"),
        {"name": "Permit", "description": "Permit document", "aliases": []},
    ]
