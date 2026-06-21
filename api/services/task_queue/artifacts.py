"""Task queue processing artifact helpers."""

from __future__ import annotations

from config import get_settings
from services.processing_artifacts import ProcessingArtifactService


def _processing_artifacts() -> ProcessingArtifactService:
    return ProcessingArtifactService(get_settings().EXTRACTED_DATA_DIR)
