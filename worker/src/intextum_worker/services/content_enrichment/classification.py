"""GLiNER2 document classification provider."""

from __future__ import annotations

from typing import Any

from intextum_worker.models import (
    WorkerDocumentClassificationLabel,
    WorkerDocumentClassificationResult,
)
from intextum_worker.services.content_enrichment_utils import (
    MAX_FIELD_EVIDENCE,
    _find_local_evidence_for_terms,
    _normalize_text,
    _resolve_classification_confidence,
    _resolve_classification_label,
)

from . import model_artifacts
from .registry import GLINER2_PROVIDER, DocumentClassificationProviderConfig

_IMPLICIT_OTHER_DOCUMENT_LABEL = "No matching document class"


def _classification_label_names(
    labels: list[WorkerDocumentClassificationLabel],
) -> list[str]:
    """Return labels for GLiNER2 with an explicit non-match fallback."""
    label_names = [label.name.strip() for label in labels if label.name.strip()]
    if _IMPLICIT_OTHER_DOCUMENT_LABEL not in label_names:
        return [*label_names, _IMPLICIT_OTHER_DOCUMENT_LABEL]
    return label_names


def _classification_label_description(
    label: WorkerDocumentClassificationLabel,
) -> str | None:
    parts = []
    if label.description.strip():
        parts.append(label.description.strip())
    aliases = [alias.strip() for alias in label.aliases if alias.strip()]
    if aliases:
        parts.append(f"Also known as: {', '.join(aliases)}")
    return ". ".join(parts) if parts else None


def _classification_task_config(
    labels: list[WorkerDocumentClassificationLabel],
) -> dict[str, Any]:
    label_names = _classification_label_names(labels)
    label_descriptions = {
        label.name.strip(): description
        for label in labels
        if label.name.strip()
        for description in [_classification_label_description(label)]
        if description is not None
    }
    label_descriptions[_IMPLICIT_OTHER_DOCUMENT_LABEL] = (
        "Use this when the document does not clearly match any configured class."
    )
    return {
        "labels": label_names,
        "multi_label": False,
        "label_descriptions": label_descriptions,
    }


def _classification_label_by_name(
    labels: list[WorkerDocumentClassificationLabel],
) -> dict[str, WorkerDocumentClassificationLabel]:
    return {label.name.strip().lower(): label for label in labels if label.name.strip()}


def _classify_document_gliner2(
    text: str,
    *,
    model_name: str,
    labels: list[WorkerDocumentClassificationLabel],
    chunks: list[Any] | None = None,
    provider_name: str = GLINER2_PROVIDER,
    task_id: str | None = None,
    task_secret: str | None = None,
) -> WorkerDocumentClassificationResult:
    """Classify one document into an admin-defined class."""
    if not labels:
        return WorkerDocumentClassificationResult(
            status="skipped",
            provider=provider_name,
            source="configuration",
            error="No document classification labels configured",
        )

    normalized = _normalize_text(text, max_chars=8_000)
    if not normalized:
        return WorkerDocumentClassificationResult(
            status="skipped",
            provider=provider_name,
            source="content",
            error="Document text was empty after normalization",
        )

    extractor = model_artifacts._load_extractor(
        model_name,
        task_id=task_id,
        task_secret=task_secret,
    )
    configured_label_by_name = _classification_label_by_name(labels)
    classification_task = _classification_task_config(labels)
    raw_output = extractor.classify_text(
        normalized,
        {"document_class": classification_task},
        include_confidence=True,
    )
    resolved_label = _resolve_classification_label(raw_output)

    if not resolved_label:
        return WorkerDocumentClassificationResult(
            status="failed",
            provider=provider_name,
            model=model_name,
            raw_output=raw_output if isinstance(raw_output, dict) else None,
            error="GLiNER2 classification did not return a document class",
        )

    confidence = _resolve_classification_confidence(
        raw_output,
        label=resolved_label,
    )
    resolved_label_config = configured_label_by_name.get(resolved_label.strip().lower())
    if resolved_label_config is None:
        return WorkerDocumentClassificationResult(
            status="skipped",
            source="model",
            provider=provider_name,
            model=model_name,
            confidence=confidence,
            raw_output=raw_output if isinstance(raw_output, dict) else None,
            error="GLiNER2 classification did not select a configured document class",
        )

    evidence_terms = [
        resolved_label,
        *resolved_label_config.aliases,
    ]
    evidence = _find_local_evidence_for_terms(
        chunks,
        evidence_terms,
        max_items=MAX_FIELD_EVIDENCE,
    )

    return WorkerDocumentClassificationResult(
        status="completed",
        source="model",
        provider=provider_name,
        model=model_name,
        class_id=resolved_label_config.id or None,
        label=resolved_label,
        confidence=confidence,
        evidence=evidence,
        raw_output=raw_output if isinstance(raw_output, dict) else None,
    )


class GlinerDocumentClassificationProvider:
    """GLiNER2-backed document classification provider."""

    key = GLINER2_PROVIDER

    def classify(
        self,
        text: str,
        *,
        labels: list[WorkerDocumentClassificationLabel],
        chunks: list[Any] | None,
        config: DocumentClassificationProviderConfig,
    ) -> WorkerDocumentClassificationResult:
        return _classify_document_gliner2(
            text,
            model_name=config.model_name,
            labels=labels,
            chunks=chunks,
            provider_name=config.provider,
            task_id=config.task_id,
            task_secret=config.task_secret,
        )
