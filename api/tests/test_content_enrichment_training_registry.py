"""Validation tests for content-enrichment fine-tune requests."""

from __future__ import annotations

import pytest

from models.ai_settings import EffectiveAiSettings
from models.content.enrichment_training import (
    CreateContentEnrichmentFineTuneJobRequest,
)
from services.ai_settings import AiSettingsService
from services.content_enrichment_training.registry import (
    ContentEnrichmentTrainingRegistry,
)


def _settings_with_classification_labels() -> EffectiveAiSettings:
    base = AiSettingsService._base_defaults().model_dump(mode="json")
    return EffectiveAiSettings.model_validate(
        {
            **base,
            "document_classification_labels": [
                {"name": "Invoice", "description": "Invoice documents", "aliases": []}
            ],
        }
    )


def test_validate_request_rejects_schema_target_for_classification_training():
    settings = _settings_with_classification_labels()

    with pytest.raises(ValueError, match="does not accept a target schema"):
        ContentEnrichmentTrainingRegistry.validate_request(
            CreateContentEnrichmentFineTuneJobRequest(
                target_kind="classification",
                target_name="invoice_header",
            ),
            settings,
        )


def test_validate_request_accepts_classification_training():
    settings = _settings_with_classification_labels()

    # Must not raise.
    ContentEnrichmentTrainingRegistry.validate_request(
        CreateContentEnrichmentFineTuneJobRequest(target_kind="classification"),
        settings,
    )
