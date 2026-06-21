"""Public content enrichment orchestration entrypoints."""

from __future__ import annotations

from typing import Any

from models import (
    WorkerDocumentClassificationLabel,
    WorkerDocumentClassificationResult,
)

from .classification import GlinerDocumentClassificationProvider
from .langgraph_provider import LangGraphExtractionProvider
from .merge import describe_document_extraction_plan, extract_document_data
from .registry import (
    GLINER2_PROVIDER,
    DocumentClassificationProviderConfig,
    EnrichmentProviderRegistry,
    UnknownEnrichmentProvider,
)

_PROVIDER_REGISTRY = EnrichmentProviderRegistry()
_PROVIDER_REGISTRY.register_classification(GlinerDocumentClassificationProvider())
_PROVIDER_REGISTRY.register_extraction(LangGraphExtractionProvider())


def classify_document(
    text: str,
    *,
    model_name: str,
    labels: list[WorkerDocumentClassificationLabel],
    chunks: list[Any] | None = None,
    provider_name: str = GLINER2_PROVIDER,
    task_id: str | None = None,
    task_secret: str | None = None,
) -> WorkerDocumentClassificationResult:
    """Classify one document through the configured provider."""
    try:
        provider = _PROVIDER_REGISTRY.classification(provider_name)
    except UnknownEnrichmentProvider as exc:
        return WorkerDocumentClassificationResult(
            status="failed",
            source="configuration",
            provider=provider_name,
            model=model_name,
            error=str(exc),
        )
    return provider.classify(
        text,
        labels=labels,
        chunks=chunks,
        config=DocumentClassificationProviderConfig(
            provider=provider_name,
            model_name=model_name,
            task_id=task_id,
            task_secret=task_secret,
        ),
    )


__all__ = [
    "classify_document",
    "describe_document_extraction_plan",
    "extract_document_data",
]
