"""Provider interfaces and registry for worker-side document enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from intextum_worker.models import (
    WorkerDocumentClassificationLabel,
    WorkerDocumentClassificationResult,
    WorkerDocumentExtractionResult,
    WorkerDocumentExtractionSchema,
)

GLINER2_PROVIDER = "gliner2"
LANGGRAPH_EXTRACT_PROVIDER = "langgraph_extract"


class UnknownEnrichmentProvider(ValueError):
    """Raised when runtime config references an unknown enrichment provider."""


@dataclass(frozen=True)
class DocumentClassificationProviderConfig:
    """Provider-independent classification execution settings."""

    provider: str
    model_name: str
    task_id: str | None = None
    task_secret: str | None = None


@dataclass(frozen=True)
class DocumentExtractionProviderConfig:
    """Provider-independent extraction execution settings."""

    provider: str
    model_name: str
    max_chars: int
    task_id: str | None = None
    task_secret: str | None = None
    max_output_tokens: int = 2048
    chunk_strategy: str = "full"
    chat_max_retries: int = 2
    chat_evidence_required: bool = True
    chat_full_text_threshold_chars: int = 20_000


class DocumentClassificationProvider(Protocol):
    """Classifies one document into one configured class."""

    key: str

    def classify(
        self,
        text: str,
        *,
        labels: list[WorkerDocumentClassificationLabel],
        chunks: list[Any] | None,
        config: DocumentClassificationProviderConfig,
    ) -> WorkerDocumentClassificationResult:
        """Return one normalized worker classification result."""


class DocumentExtractionProvider(Protocol):
    """Extracts schema-owned structured data for one selected document class."""

    key: str

    def extract(
        self,
        text: str,
        *,
        schema: WorkerDocumentExtractionSchema,
        document_class: str | None,
        document_class_id: str | None,
        chunks: list[Any] | None,
        config: DocumentExtractionProviderConfig,
    ) -> WorkerDocumentExtractionResult:
        """Return one normalized worker extraction result."""


class EnrichmentProviderRegistry:
    """Small explicit registry for built-in enrichment providers."""

    def __init__(self) -> None:
        self._classification: dict[str, DocumentClassificationProvider] = {}
        self._extraction: dict[str, DocumentExtractionProvider] = {}

    def register_classification(
        self,
        provider: DocumentClassificationProvider,
    ) -> None:
        self._classification[provider.key] = provider

    def register_extraction(self, provider: DocumentExtractionProvider) -> None:
        self._extraction[provider.key] = provider

    def classification(self, key: str) -> DocumentClassificationProvider:
        provider = self._classification.get(key)
        if provider is None:
            raise UnknownEnrichmentProvider(
                f"Unknown document classification provider: {key}"
            )
        return provider

    def extraction(self, key: str) -> DocumentExtractionProvider:
        provider = self._extraction.get(key)
        if provider is None:
            raise UnknownEnrichmentProvider(
                f"Unknown document extraction provider: {key}"
            )
        return provider
