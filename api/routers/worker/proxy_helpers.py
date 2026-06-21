"""Pure helper functions for worker proxy endpoints."""

import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from services.ai_limits import create_embedding_response
from services.content_enrichment_training import (
    parse_content_enrichment_registry_model_ref,
)
from models.vector import VectorChunkUpsert
from models.worker import (
    VectorPoint,
    WorkerVlmImageContent,
    WorkerVlmImageUrl,
    WorkerVlmMessage,
    WorkerVlmProxyPayload,
    WorkerVlmTextContent,
)

from .helpers import assert_path_within_root

DEFAULT_VLM_SEED = 42
DEFAULT_VLM_MAX_COMPLETION_TOKENS = 1024
MAX_VLM_MAX_COMPLETION_TOKENS = 2048
DEFAULT_VLM_TIMEOUT_SECONDS = 300.0
VLM_UPSTREAM_TIMEOUT_GRACE_SECONDS = 10.0
DEFAULT_WORKER_EMBEDDING_MAX_TEXTS = 512
DEFAULT_WORKER_EMBEDDING_MAX_TEXT_CHARS = 100_000
DEFAULT_WORKER_EMBEDDING_MAX_TOTAL_CHARS = 1_000_000


def _chunk_data_from_point(point: VectorPoint) -> VectorChunkUpsert:
    return VectorChunkUpsert(
        id=point.id,
        text=point.payload.text,
        embedding=point.vector,
        chunk_index=point.payload.chunk_index,
        page_numbers=point.payload.page_numbers,
        headings=point.payload.headings,
        images=point.payload.images,
        doc_refs=point.payload.doc_refs,
        index_version=point.payload.index_version,
    )


def _effective_registry_model_ids(ai_settings: object) -> set[str]:
    model_ids: set[str] = set()
    for model_name in (
        getattr(ai_settings, "document_classification_model", None),
        getattr(ai_settings, "document_extraction_model", None),
    ):
        registry_id = parse_content_enrichment_registry_model_ref(model_name)
        if registry_id:
            model_ids.add(registry_id)
    schema_models = getattr(ai_settings, "document_extraction_schema_models", {})
    if isinstance(schema_models, dict):
        for model_name in schema_models.values():
            registry_id = parse_content_enrichment_registry_model_ref(model_name)
            if registry_id:
                model_ids.add(registry_id)
    return model_ids


def _resolve_content_enrichment_artifact_file(
    artifacts_root: Path,
    artifact_path: str,
) -> Path:
    """Resolve the configured artifact path inside the artifact root."""
    artifact_file = (artifacts_root / artifact_path).resolve()
    assert_path_within_root(artifact_file, artifacts_root)
    return artifact_file


def _extract_single_image_data_url(messages: list[WorkerVlmMessage]) -> str:
    """Extract exactly one data URI image URL from OpenAI-style messages."""
    if len(messages) != 1:
        raise HTTPException(status_code=400, detail="Exactly one message is required")

    message = messages[0]
    if message.role != "user":
        raise HTTPException(
            status_code=400, detail="Only a single user message is allowed"
        )

    image_urls: list[str] = []
    for item in message.content:
        if not isinstance(item, WorkerVlmImageContent):
            continue
        image_urls.append(item.image_url.url)

    if len(image_urls) != 1:
        raise HTTPException(
            status_code=400,
            detail="Exactly one image_url content item is required",
        )

    image_url = image_urls[0]
    if not image_url.startswith("data:image/") or ";base64," not in image_url:
        raise HTTPException(
            status_code=400,
            detail="Only data URI image payloads are allowed",
        )

    return image_url


def _build_vlm_payload(
    *,
    model: str,
    prompt: str,
    image_data_url: str,
    max_completion_tokens: int,
    seed: int | None,
    enable_thinking: bool,
) -> WorkerVlmProxyPayload:
    return WorkerVlmProxyPayload(
        model=model,
        seed=seed if seed is not None else DEFAULT_VLM_SEED,
        max_tokens=max_completion_tokens,
        chat_template_kwargs={"enable_thinking": enable_thinking},
        messages=[
            WorkerVlmMessage(
                role="user",
                content=[
                    WorkerVlmImageContent(
                        type="image_url",
                        image_url=WorkerVlmImageUrl(url=image_data_url),
                    ),
                    WorkerVlmTextContent(
                        type="text",
                        text=prompt,
                    ),
                ],
            )
        ],
    )


def _validated_max_completion_tokens(value: int | None) -> int:
    """Validate and normalize max_completion_tokens for worker VLM calls."""
    if value is None:
        return DEFAULT_VLM_MAX_COMPLETION_TOKENS
    if value < 1 or value > MAX_VLM_MAX_COMPLETION_TOKENS:
        raise HTTPException(
            status_code=400,
            detail=(
                "max_completion_tokens must be between 1 and "
                f"{MAX_VLM_MAX_COMPLETION_TOKENS}"
            ),
        )
    return value


def _empty_vlm_chat_response(
    *, reason: str, model: str = "skipped-task-invalid"
) -> dict:
    """Return an OpenAI-compatible empty response when VLM description is unavailable."""
    return {
        "id": f"chatcmpl-skipped-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "metadata": {"skipped": True, "reason": reason},
    }


def _picture_description_timeout_seconds(settings: object) -> float:
    raw_value = getattr(
        settings,
        "PICTURE_DESCRIPTION_TIMEOUT_SECONDS",
        DEFAULT_VLM_TIMEOUT_SECONDS,
    )
    if not isinstance(raw_value, int | float | str):
        return DEFAULT_VLM_TIMEOUT_SECONDS
    try:
        timeout_seconds = float(raw_value)
    except (TypeError, ValueError):
        timeout_seconds = DEFAULT_VLM_TIMEOUT_SECONDS
    return max(1.0, timeout_seconds)


def _picture_description_upstream_timeout_seconds(settings: object) -> float:
    timeout_seconds = _picture_description_timeout_seconds(settings)
    return max(1.0, timeout_seconds - VLM_UPSTREAM_TIMEOUT_GRACE_SECONDS)


def _picture_description_chat_completions_url(settings: object) -> str:
    base_url = _settings_string(
        settings,
        "PICTURE_DESCRIPTION_URL",
        "http://localhost:11434",
    ).rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def _content_enrichment_stage_timeout_seconds(settings: object) -> float:
    raw_value = getattr(settings, "CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS", 300.0)
    if not isinstance(raw_value, int | float | str):
        return 300.0
    try:
        timeout_seconds = float(raw_value)
    except (TypeError, ValueError):
        return 300.0
    return max(0.0, timeout_seconds)


def _content_enrichment_upstream_timeout_seconds(settings: object) -> float | None:
    timeout_seconds = _content_enrichment_stage_timeout_seconds(settings)
    return None if timeout_seconds <= 0 else timeout_seconds


def _settings_string(settings: object, attr_name: str, default: str) -> str:
    raw_value = getattr(settings, attr_name, default)
    return raw_value if isinstance(raw_value, str) else default


def _settings_positive_int(settings: object, attr_name: str, default: int) -> int:
    raw_value = getattr(settings, attr_name, default)
    if not isinstance(raw_value, int | float | str):
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _json_payloads(items: list[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


def _worker_config_payload(settings: object, ai_settings: object) -> dict[str, Any]:
    return {
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_max_tokens": settings.EMBEDDING_MAX_TOKENS,
        "embedding_vector_size": settings.EMBEDDING_VECTOR_SIZE,
        "picture_description_model": ai_settings.picture_description_model,
        "picture_description_prompt": ai_settings.picture_description_prompt,
        "picture_description_max_tokens": ai_settings.picture_description_max_tokens,
        "picture_description_timeout_seconds": _picture_description_timeout_seconds(
            settings
        ),
        "document_classification_enabled": ai_settings.document_classification_enabled,
        "document_classification_provider": (
            ai_settings.document_classification_provider
        ),
        "document_classification_model": ai_settings.document_classification_model,
        "document_classification_labels": _json_payloads(
            ai_settings.document_classification_labels
        ),
        "document_extraction_enabled": ai_settings.document_extraction_enabled,
        "document_extraction_model": ai_settings.document_extraction_model,
        "document_extraction_llm_model": ai_settings.document_extraction_llm_model,
        "document_extraction_llm_max_output_tokens": (
            ai_settings.document_extraction_llm_max_output_tokens
        ),
        "document_extraction_chunk_strategy": (
            ai_settings.document_extraction_chunk_strategy
        ),
        "document_extraction_chat_max_retries": (
            ai_settings.document_extraction_chat_max_retries
        ),
        "document_extraction_chat_evidence_required": (
            ai_settings.document_extraction_chat_evidence_required
        ),
        "document_extraction_chat_full_text_threshold_chars": (
            ai_settings.document_extraction_chat_full_text_threshold_chars
        ),
        "content_enrichment_stage_timeout_seconds": (
            _content_enrichment_stage_timeout_seconds(settings)
        ),
        "document_extraction_schema_models": (
            ai_settings.document_extraction_schema_models
        ),
        "document_extraction_schemas": _json_payloads(
            ai_settings.document_extraction_schemas
        ),
        "document_extraction_max_chars": ai_settings.document_extraction_max_chars,
    }


def _chat_completions_url(settings: object) -> str:
    base_url = _settings_string(
        settings, "CHAT_API_BASE", "http://localhost:11434/v1"
    ).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=500,
            detail="CHAT_API_BASE must use http:// or https:// scheme",
        )
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _document_extraction_llm_upstream_request(
    *,
    settings: object,
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, str], float | None, bool]:
    upstream_payload = dict(payload)
    client_requested_stream = bool(upstream_payload.get("stream"))
    headers = {
        "Authorization": (
            f"Bearer {_settings_string(settings, 'CHAT_API_KEY', 'ollama')}"
        ),
        "Content-Type": "application/json",
    }
    return (
        _chat_completions_url(settings),
        upstream_payload,
        headers,
        _content_enrichment_upstream_timeout_seconds(settings),
        client_requested_stream,
    )


async def _create_embedding_response(
    client: object,
    settings: object,
    *,
    model: str,
    texts: list[str],
) -> object:
    return await create_embedding_response(
        client,
        settings,
        model=model,
        texts=texts,
    )


def _sorted_embedding_data(response: object) -> list[object]:
    return sorted(response.data, key=lambda embedding: embedding.index)


def _sorted_embedding_vectors(response: object) -> list[list[float]]:
    return [item.embedding for item in _sorted_embedding_data(response)]


def _embeddings_by_index(response: object) -> dict[int, list[float]]:
    return {item.index: item.embedding for item in _sorted_embedding_data(response)}


def _prompt_token_count(response: object) -> int:
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    if prompt_tokens is None:
        raise HTTPException(
            status_code=502,
            detail=(
                "Embedding provider did not return token usage. "
                "Cannot perform strict chunk tokenization."
            ),
        )
    return int(prompt_tokens)


def _validate_worker_texts(texts: list[str], settings: object) -> list[str]:
    if not texts:
        raise HTTPException(status_code=400, detail="texts must not be empty")

    max_texts = _settings_positive_int(
        settings,
        "WORKER_EMBEDDING_MAX_TEXTS",
        DEFAULT_WORKER_EMBEDDING_MAX_TEXTS,
    )
    max_text_chars = _settings_positive_int(
        settings,
        "WORKER_EMBEDDING_MAX_TEXT_CHARS",
        DEFAULT_WORKER_EMBEDDING_MAX_TEXT_CHARS,
    )
    max_total_chars = _settings_positive_int(
        settings,
        "WORKER_EMBEDDING_MAX_TOTAL_CHARS",
        DEFAULT_WORKER_EMBEDDING_MAX_TOTAL_CHARS,
    )
    if len(texts) > max_texts:
        raise HTTPException(
            status_code=413,
            detail=f"texts exceeds max item count of {max_texts}",
        )
    total_chars = 0
    for text in texts:
        text_chars = len(text)
        if text_chars > max_text_chars:
            raise HTTPException(
                status_code=413,
                detail=f"text exceeds max length of {max_text_chars} characters",
            )
        total_chars += text_chars
    if total_chars > max_total_chars:
        raise HTTPException(
            status_code=413,
            detail=f"texts exceeds max total length of {max_total_chars} characters",
        )
    return texts
