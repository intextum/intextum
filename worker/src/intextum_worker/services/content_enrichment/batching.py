"""Field batching and retry policy for chat extraction."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from intextum_worker.models import WorkerDocumentExtractionSchema

from .registry import DocumentExtractionProviderConfig

logger = logging.getLogger(__name__)

_MAX_OUTPUT_TOKENS_GROWTH_FACTOR = 4

StreamingLlmCall = Callable[..., tuple[str, str | None]]


def _field_batches(
    schema: WorkerDocumentExtractionSchema,
    target_field_names: list[str],
    missing_required: list[str] | None = None,
) -> list[list[str]]:
    """Partition target fields so each LLM call produces a tractable JSON.

    Scalars batch together; list/object_list fields go alone so a long repeated
    field never fights for output budget with other fields. On retry-pass-2 we
    only re-issue calls for batches that contain a missing required field.
    """
    target_set = set(target_field_names)
    scalar_batch: list[str] = []
    repeated_batches: list[list[str]] = []
    for field in schema.fields:
        if field.name not in target_set:
            continue
        if field.dtype in {"list", "object_list"}:
            repeated_batches.append([field.name])
        else:
            scalar_batch.append(field.name)
    batches = []
    if scalar_batch:
        batches.append(scalar_batch)
    batches.extend(repeated_batches)
    if missing_required:
        missing_set = set(missing_required)
        batches = [
            batch for batch in batches if any(name in missing_set for name in batch)
        ]
    return batches


def _call_llm_with_length_retry(
    *,
    call_llm_streaming: StreamingLlmCall,
    client: Any,
    config: DocumentExtractionProviderConfig,
    system_message: str,
    user_message: str,
    response_format: dict[str, Any],
    schema_name: str,
    batch: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    """Call the LLM, doubling the token budget on finish_reason=='length'.

    Returns the final message and a per-attempt log (each entry carrying its
    own finish_reason) so the caller can record every try in raw_llm_outputs.
    """
    base_tokens = max(1, config.max_output_tokens)
    token_ceiling = base_tokens * _MAX_OUTPUT_TOKENS_GROWTH_FACTOR
    attempts: list[dict[str, Any]] = []
    current_tokens = base_tokens
    while True:
        message, finish_reason = call_llm_streaming(
            client=client,
            config=config,
            system_message=system_message,
            user_message=user_message,
            response_format=response_format,
            max_output_tokens=current_tokens,
        )
        attempts.append(
            {
                "finish_reason": finish_reason,
                "content": message,
                "max_output_tokens": current_tokens,
                "response_format_type": response_format.get("type"),
            }
        )
        if finish_reason != "length":
            return message, attempts
        if current_tokens >= token_ceiling:
            logger.warning(
                "Chat extraction still truncated at token ceiling",
                extra={
                    "model": config.model_name,
                    "max_tokens": current_tokens,
                    "token_ceiling": token_ceiling,
                    "schema_name": schema_name,
                    "batch_fields": batch,
                },
            )
            return message, attempts
        next_tokens = min(current_tokens * 2, token_ceiling)
        logger.warning(
            "Chat extraction output truncated; retrying with larger token budget",
            extra={
                "model": config.model_name,
                "previous_max_tokens": current_tokens,
                "next_max_tokens": next_tokens,
                "schema_name": schema_name,
                "batch_fields": batch,
            },
        )
        current_tokens = next_tokens
