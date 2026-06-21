"""Schema-driven dispatch for document extraction."""

from __future__ import annotations

from typing import Any

from intextum_worker.models import (
    WorkerDocumentExtractionResult,
    WorkerDocumentExtractionSchema,
)
from intextum_worker.services.content_enrichment_utils import _pick_schema

from .langgraph_provider import LangGraphExtractionProvider
from .registry import (
    LANGGRAPH_EXTRACT_PROVIDER,
    DocumentExtractionProviderConfig,
)

_EXTRACTION_PROVIDER = LangGraphExtractionProvider()


def _resolve_extraction_model_name(
    default_model_name: str,
    *,
    schema_id: str,
    schema_name: str,
    schema_models: dict[str, str] | None,
) -> str:
    """Pick the per-schema model override.

    Prefers a lookup by ``schema_id`` so the override survives a rename. Falls
    back to ``schema_name`` for back-compat with existing configs that were
    keyed by name before this fix.
    """
    if not isinstance(schema_models, dict):
        return default_model_name
    for key in (schema_id, schema_name):
        if not key:
            continue
        override = schema_models.get(key)
        if isinstance(override, str) and override.strip():
            return override.strip()
    return default_model_name


def _available_schema_summaries(
    schemas: list[WorkerDocumentExtractionSchema],
) -> list[dict[str, Any]]:
    return [
        {
            "schema_id": schema.id or None,
            "schema_name": schema.name,
            "document_class_id": schema.document_class_id or None,
            "document_class": schema.document_class,
            "field_count": len(schema.fields),
        }
        for schema in schemas
    ]


def describe_document_extraction_plan(
    *,
    model_name: str,
    llm_model_name: str | None = None,
    schemas: list[WorkerDocumentExtractionSchema],
    document_class: str | None,
    document_class_id: str | None = None,
    schema_models: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Describe the schema match and routing before extraction runs."""
    schema = _pick_schema(
        schemas,
        document_class=document_class,
        document_class_id=document_class_id,
    )
    if schema is None:
        return {
            "schema_matched": False,
            "provider": None,
            "model": None,
            "providers": [],
            "models": [],
            "schema_id": None,
            "schema_name": None,
            "schema_document_class_id": None,
            "schema_document_class": None,
            "field_count": 0,
            "field_groups": [],
            "available_schemas": _available_schema_summaries(schemas),
        }

    effective_model_name = _resolve_extraction_model_name(
        model_name,
        schema_id=schema.id or "",
        schema_name=schema.name,
        schema_models=schema_models,
    )
    chat_model_name = (
        llm_model_name or effective_model_name
    ).strip() or effective_model_name
    field_groups = [
        {
            "provider": LANGGRAPH_EXTRACT_PROVIDER,
            "model": chat_model_name,
            "field_count": len(schema.fields),
            "fields": [field.name for field in schema.fields],
        }
    ]
    return {
        "schema_matched": True,
        "provider": LANGGRAPH_EXTRACT_PROVIDER,
        "model": chat_model_name,
        "providers": [LANGGRAPH_EXTRACT_PROVIDER],
        "models": [chat_model_name],
        "schema_id": schema.id or None,
        "schema_name": schema.name,
        "schema_document_class_id": schema.document_class_id or None,
        "schema_document_class": schema.document_class,
        "field_count": len(schema.fields),
        "field_groups": field_groups,
        "available_schemas": _available_schema_summaries(schemas),
    }


def extract_document_data(
    text: str,
    *,
    model_name: str,
    llm_model_name: str | None = None,
    schemas: list[WorkerDocumentExtractionSchema],
    document_class: str | None,
    document_class_id: str | None = None,
    max_chars: int,
    llm_max_output_tokens: int = 2048,
    chunk_strategy: str = "full",
    chat_max_retries: int = 2,
    chat_evidence_required: bool = True,
    chat_full_text_threshold_chars: int = 20_000,
    schema_models: dict[str, str] | None = None,
    chunks: list[Any] | None = None,
    task_id: str | None = None,
    task_secret: str | None = None,
) -> WorkerDocumentExtractionResult:
    """Extract structured data for one document via the chat extraction provider."""
    schema = _pick_schema(
        schemas,
        document_class=document_class,
        document_class_id=document_class_id,
    )
    if schema is None:
        error = (
            "No document class selected for schema-based extraction"
            if not (document_class_id or document_class)
            else "No extraction schema matches the selected document class"
        )
        return WorkerDocumentExtractionResult(
            status="skipped",
            provider=LANGGRAPH_EXTRACT_PROVIDER,
            model=model_name,
            document_class=document_class,
            error=error,
            raw_output={
                "available_schemas": _available_schema_summaries(schemas),
                "document_class_id": document_class_id,
                "document_class": document_class,
            },
        )

    effective_model_name = _resolve_extraction_model_name(
        model_name,
        schema_id=schema.id or "",
        schema_name=schema.name,
        schema_models=schema_models,
    )
    chat_model_name = (
        llm_model_name or effective_model_name
    ).strip() or effective_model_name

    return _EXTRACTION_PROVIDER.extract(
        text,
        schema=schema,
        document_class=document_class,
        document_class_id=document_class_id,
        chunks=chunks,
        config=DocumentExtractionProviderConfig(
            provider=LANGGRAPH_EXTRACT_PROVIDER,
            model_name=chat_model_name,
            max_chars=max_chars,
            task_id=task_id,
            task_secret=task_secret,
            max_output_tokens=llm_max_output_tokens,
            chunk_strategy=chunk_strategy,
            chat_max_retries=chat_max_retries,
            chat_evidence_required=chat_evidence_required,
            chat_full_text_threshold_chars=chat_full_text_threshold_chars,
        ),
    )
