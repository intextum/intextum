"""Tests for typed AI settings pydantic models."""

import pytest
from pydantic import ValidationError

from models.ai_settings import (
    DocumentExtractionExample,
    DocumentExtractionScene,
    DocumentExtractionSceneExtraction,
    DocumentExtractionSchemaInput,
)


def test_extraction_example_accepts_anchor_substring_of_text():
    example = DocumentExtractionExample(
        text="Due date is 2026-04-29.",
        value="2026-04-29",
        extraction_text="2026-04-29",
    )
    assert example.extraction_text == "2026-04-29"


def test_extraction_example_normalizes_blank_anchor_to_none():
    example = DocumentExtractionExample(
        text="Due date is 2026-04-29.",
        value="2026-04-29",
        extraction_text="   ",
    )
    assert example.extraction_text is None


def test_extraction_example_rejects_anchor_not_in_text():
    with pytest.raises(ValidationError) as exc_info:
        DocumentExtractionExample(
            text="Due date is 2026-04-29.",
            value="2026-04-29",
            extraction_text="never appears here",
        )
    assert "extraction_text_must_be_substring_of_text" in str(exc_info.value)


def test_extraction_example_omits_anchor_when_unset():
    example = DocumentExtractionExample(
        text="Due date is 2026-04-29.",
        value="2026-04-29",
    )
    assert example.extraction_text is None


def test_scene_requires_extraction_anchor_in_text():
    scene = DocumentExtractionScene(
        text="ROMEO. But soft! What light through yonder window breaks?",
        extractions=[
            DocumentExtractionSceneExtraction(
                field="character",
                extraction_text="ROMEO",
                value={"name": "ROMEO"},
            ),
        ],
    )
    assert scene.extractions[0].extraction_text == "ROMEO"


def test_scene_rejects_extraction_anchor_not_in_text():
    with pytest.raises(ValidationError) as exc_info:
        DocumentExtractionScene(
            text="ROMEO. But soft!",
            extractions=[
                DocumentExtractionSceneExtraction(
                    field="character",
                    extraction_text="JULIET",
                    value={"name": "JULIET"},
                ),
            ],
        )
    assert "scene_extraction_anchor_must_be_substring_of_text" in str(exc_info.value)


def test_schema_rejects_scene_extraction_referencing_unknown_field():
    with pytest.raises(ValidationError) as exc_info:
        DocumentExtractionSchemaInput.model_validate(
            {
                "name": "literature_fields",
                "document_class": "Romeo and Juliet",
                "fields": [
                    {
                        "name": "character",
                        "dtype": "object_list",
                        "description": "Character mentioned in the scene",
                        "fields": [
                            {
                                "name": "name",
                                "dtype": "str",
                                "description": "Character name",
                            },
                        ],
                        "examples": [
                            {
                                "text": "ROMEO speaks.",
                                "value": {"name": "ROMEO"},
                                "extraction_text": "ROMEO",
                            },
                        ],
                    },
                ],
                "scenes": [
                    {
                        "text": "ROMEO. But soft!",
                        "extractions": [
                            {
                                "field": "emotion",
                                "extraction_text": "But soft!",
                                "value": "wonder",
                            },
                        ],
                    },
                ],
            }
        )
    assert "scene_extraction_field_unknown" in str(exc_info.value)


def test_schema_accepts_scene_extraction_for_known_field():
    schema = DocumentExtractionSchemaInput.model_validate(
        {
            "name": "literature_fields",
            "document_class": "Romeo and Juliet",
            "fields": [
                {
                    "name": "character",
                    "dtype": "object_list",
                    "description": "Character mentioned in the scene",
                    "fields": [
                        {
                            "name": "name",
                            "dtype": "str",
                            "description": "Character name",
                        },
                    ],
                    "examples": [
                        {
                            "text": "ROMEO speaks.",
                            "value": {"name": "ROMEO"},
                            "extraction_text": "ROMEO",
                        },
                    ],
                },
            ],
            "scenes": [
                {
                    "text": "ROMEO. But soft!",
                    "extractions": [
                        {
                            "field": "character",
                            "extraction_text": "ROMEO",
                            "value": {"name": "ROMEO"},
                        },
                    ],
                },
            ],
        }
    )
    assert len(schema.scenes) == 1
    assert schema.scenes[0].extractions[0].field == "character"
