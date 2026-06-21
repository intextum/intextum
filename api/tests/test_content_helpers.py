from unittest.mock import AsyncMock

import pytest

from models.sqlalchemy_models import ContentItemEnrichmentState
from routers.content.helpers import (
    _processing_config_with_current_class_override,
)
from services.content.docling import classify_images_from_docling
from routers.content.extracted import (
    _docling_document_for_viewer,
    _resolve_extracted_dir_for_content_item,
)
from services.content.helpers import summarize_processing_mode


def test_summarize_processing_mode_returns_none_without_config():
    assert summarize_processing_mode(None) is None


def test_summarize_processing_mode_marks_full_processing():
    summary = summarize_processing_mode({"do_ocr": True, "document_enrichment": True})

    assert summary is not None
    assert summary.mode == "full"
    assert summary.enrichment_only is False
    assert summary.document_enrichment is True


def test_summarize_processing_mode_marks_enrichment_only_as_combined_refresh():
    summary = summarize_processing_mode(
        {
            "enrichment_only": True,
            "document_enrichment": False,
        }
    )

    assert summary is not None
    assert summary.mode == "enrichment_only"
    assert summary.document_enrichment is True


def test_classify_images_from_docling_uses_meta_predictions_for_picture_tables():
    doc = {
        "pictures": [
            {
                "image": {"uri": "media/table_picture.png"},
                "meta": {
                    "classification": {
                        "predictions": [
                            {"class_name": "table", "confidence": 0.98},
                        ]
                    }
                },
            },
            {
                "image": {"uri": "media/figure.png"},
                "meta": {
                    "classification": {
                        "predictions": [
                            {"class_name": "natural_image", "confidence": 0.91},
                        ]
                    }
                },
            },
        ]
    }

    assert classify_images_from_docling(doc) == {
        "table_picture.png": "table",
        "figure.png": "figure",
    }


def test_classify_images_from_docling_uses_alternate_prediction_shapes():
    doc = {
        "pictures": [
            {
                "image": {"uri": "media/table_picture.png"},
                "meta": {
                    "classification": {
                        "predicted_classes": [
                            {"name": "table", "probability": 0.8},
                        ]
                    }
                },
            },
            {
                "image": {"uri": "media/list_shape.png"},
                "meta": {
                    "classification": [
                        {"label": "document_index", "score": 0.9},
                    ]
                },
            },
        ]
    }

    assert classify_images_from_docling(doc) == {
        "table_picture.png": "table",
        "list_shape.png": "table",
    }


def test_classify_images_from_docling_uses_best_picture_prediction_only():
    doc = {
        "pictures": [
            {
                "image": {"uri": "/tmp/output/item/image_logo.png"},
                "meta": {
                    "classification": {
                        "predictions": [
                            {"class_name": "logo", "confidence": 0.99},
                            {"class_name": "table", "confidence": 0.001},
                        ]
                    }
                },
            },
            {
                "image": {"uri": "/tmp/output/item/image_table.png"},
                "meta": {
                    "classification": {
                        "predictions": [
                            {"class_name": "logo", "confidence": 0.2},
                            {"class_name": "table", "confidence": 0.93},
                        ]
                    }
                },
            },
        ]
    }

    assert classify_images_from_docling(doc) == {
        "image_logo.png": "figure",
        "image_table.png": "table",
    }


def test_docling_document_for_viewer_adds_component_annotations_without_mutating():
    doc = {
        "schema_name": "DoclingDocument",
        "pages": {
            "1": {
                "page_no": 1,
                "image": {"uri": "page_000001.png"},
                "size": {"width": 100, "height": 100},
            }
        },
        "pictures": [
            {
                "self_ref": "#/pictures/0",
                "label": "picture",
                "image": {"uri": "/tmp/worker/output/item-1/image_000001.png"},
                "meta": {
                    "classification": {
                        "predictions": [
                            {"class_name": "photograph", "confidence": 0.91}
                        ]
                    },
                    "description": {"text": "A field photo."},
                },
            }
        ],
    }

    viewer_doc = _docling_document_for_viewer(doc, content_item_id="item-1")

    assert "annotations" not in doc["pictures"][0]
    assert viewer_doc["pages"]["1"]["image"]["uri"] == (
        "/api/content/extracted-asset/item-1/page_000001.png"
    )
    assert viewer_doc["pictures"][0]["image"]["uri"] == (
        "/api/content/extracted-asset/item-1/image_000001.png"
    )
    assert viewer_doc["pictures"][0]["annotations"] == [
        {
            "kind": "classification",
            "predicted_classes": [{"class_name": "photograph", "confidence": 0.91}],
        },
        {"kind": "description", "text": "A field photo."},
    ]


def test_resolve_extracted_dir_for_content_item_uses_content_item_id(
    temp_data_dir, monkeypatch
):
    extracted_root = temp_data_dir / "extracted"
    content_item_dir = extracted_root / "content-1"
    content_item_dir.mkdir(parents=True)

    settings = type("Settings", (), {"EXTRACTED_DATA_DIR": str(extracted_root)})()
    monkeypatch.setattr("routers.content.extracted.get_settings", lambda: settings)

    assert _resolve_extracted_dir_for_content_item("content-1") == content_item_dir
    assert _resolve_extracted_dir_for_content_item("missing") is None


@pytest.mark.asyncio
async def test_enrichment_only_rerun_forces_existing_class_override():
    db = AsyncMock()
    state = ContentItemEnrichmentState(content_item_id="file-1")
    state.classification_override_class_id = "class-1"
    state.classification_override_label = "OfficialNotice"
    db.scalar.return_value = state
    processing_config = {
        "enrichment_only": True,
        "document_enrichment": True,
    }

    result = await _processing_config_with_current_class_override(
        db,
        "file-1",
        processing_config,
    )

    assert result == {
        "enrichment_only": True,
        "document_enrichment": True,
        "forced_document_class_id": "class-1",
        "forced_document_class_label": "OfficialNotice",
    }
    assert processing_config == {
        "enrichment_only": True,
        "document_enrichment": True,
    }


@pytest.mark.asyncio
async def test_enrichment_only_rerun_keeps_explicit_forced_class():
    db = AsyncMock()
    processing_config = {
        "enrichment_only": True,
        "document_enrichment": True,
        "forced_document_class_id": "class-2",
        "forced_document_class_label": "Other",
    }

    result = await _processing_config_with_current_class_override(
        db,
        "file-1",
        processing_config,
    )

    assert result is processing_config
    db.scalar.assert_not_called()


@pytest.mark.asyncio
async def test_enrichment_only_rerun_without_override_does_not_force_class():
    db = AsyncMock()
    state = ContentItemEnrichmentState(content_item_id="file-1")
    db.scalar.return_value = state
    processing_config = {
        "enrichment_only": True,
        "document_enrichment": True,
    }

    result = await _processing_config_with_current_class_override(
        db,
        "file-1",
        processing_config,
    )

    assert result is processing_config
