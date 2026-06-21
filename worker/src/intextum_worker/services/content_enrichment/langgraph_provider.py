"""Chat-style structured extraction provider built on LangGraph."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from intextum_worker.config import get_settings
from intextum_worker.models import (
    WorkerDocumentEvidence,
    WorkerDocumentExtractionField,
    WorkerDocumentExtractionFieldResult,
    WorkerDocumentExtractionResult,
    WorkerDocumentExtractionSchema,
    WorkerDocumentExtractionSummary,
)
from intextum_worker.services.content_enrichment_utils import (
    MAX_FIELD_EVIDENCE,
    _candidate_payload,
    _chunk_index_from_chunk,
    _coerce_field_value,
    _field_validation_errors,
    _normalize_text,
    _value_is_empty,
)

from .batching import _call_llm_with_length_retry, _field_batches
from .chunk_selection import _select_extraction_chunks
from .evidence_grounding import (
    _fuzzy_locate as _fuzzy_locate,
)
from .evidence_grounding import (
    _ground_anchor,
    _short_anchor,
)
from .json_response import (
    _JSON_OBJECT_RESPONSE_FORMAT,
    JsonSchemaUnsupportedError,
    _error_message_from_payload,
    _json_schema_response_format_for_batch,
    _json_schema_unsupported_message_from_text,
    _looks_like_json_schema_unsupported,
    _raise_if_json_schema_unsupported_error,
)
from .prompt import _build_prompt
from .registry import DocumentExtractionProviderConfig
from .repeated_fields import (
    _focused_repeated_field_chunks,
    _section_boundary_terms_for_schema,
)

logger = logging.getLogger(__name__)

LANGGRAPH_PROVIDER = "langgraph_extract"

_DEFAULT_FULL_TEXT_THRESHOLD = 20_000
_DEFAULT_MAX_RETRIES = 2
_CHUNK_MARKER_RE = re.compile(r"^\[Chunk (\d+)\]\s*$", flags=re.MULTILINE)


class ExtractionGraphState(TypedDict, total=False):
    """Mutable LangGraph state for chat-style extraction."""

    text: str
    chunks: list[Any] | None
    schema: WorkerDocumentExtractionSchema
    document_class: str | None
    document_class_id: str | None
    config: DocumentExtractionProviderConfig
    target_field_names: list[str]
    selected_chunks: list[Any]
    selected_text: str
    chunk_offsets: list[tuple[int, int, Any]]
    field_records: dict[str, list[dict[str, Any]]]
    missing_required: list[str]
    retry_count: int
    fallback_reasons: list[str]
    raw_llm_outputs: list[dict[str, Any]]
    error: str | None
    max_retries: int
    evidence_required: bool
    full_text_threshold_chars: int


_LLM_CONTENT_PREVIEW_CHARS = 240


def _llm_content_preview(content: str) -> str:
    """Return a bounded one-line preview for diagnostics."""
    preview = content[:_LLM_CONTENT_PREVIEW_CHARS]
    return preview.replace("\r", "\\r").replace("\n", "\\n")


def _runtime_settings(
    config: DocumentExtractionProviderConfig | None = None,
) -> tuple[int, bool, int]:
    """Read worker-side chat-extraction settings with safe fallbacks."""
    if config is not None:
        return (
            config.chat_max_retries,
            config.chat_evidence_required,
            config.chat_full_text_threshold_chars,
        )
    try:
        settings = get_settings()
    except Exception:  # pragma: no cover - defensive
        return _DEFAULT_MAX_RETRIES, True, _DEFAULT_FULL_TEXT_THRESHOLD
    return (
        int(
            getattr(
                settings, "DOCUMENT_EXTRACTION_CHAT_MAX_RETRIES", _DEFAULT_MAX_RETRIES
            )
        ),
        bool(getattr(settings, "DOCUMENT_EXTRACTION_CHAT_EVIDENCE_REQUIRED", True)),
        int(
            getattr(
                settings,
                "DOCUMENT_EXTRACTION_CHAT_FULL_TEXT_THRESHOLD_CHARS",
                _DEFAULT_FULL_TEXT_THRESHOLD,
            )
        ),
    )


def _build_openai_client(config: DocumentExtractionProviderConfig):
    """Build an OpenAI-compatible client pointing at the per-task backend proxy."""
    import openai

    settings = get_settings()
    base_url = (
        f"{settings.API_URL.rstrip('/')}"
        f"/api/worker/tasks/{config.task_id}/document-extraction-llm"
    )
    return openai.OpenAI(
        api_key=settings.WORKER_TOKEN,
        base_url=base_url,
        default_headers={"X-Task-Secret": config.task_secret or ""},
    )


def _chunks_to_selected_text(
    chunks: list[Any],
    *,
    max_chars: int | None = None,
) -> tuple[str, list[tuple[int, int, Any]], list[Any]]:
    """Concatenate chunks into one text up to max_chars, returning the chunks kept."""
    fragments: list[str] = []
    offsets: list[tuple[int, int, Any]] = []
    kept_chunks: list[Any] = []
    cursor = 0
    for index, chunk in enumerate(chunks):
        chunk_index = _chunk_index_from_chunk(chunk, index)
        marker = f"[Chunk {chunk_index}]\n"
        text = getattr(chunk, "text", "") or ""
        addition = ("\n\n" if fragments else "") + marker + text
        if max_chars is not None and cursor + len(addition) > max_chars and fragments:
            break
        start = cursor + (2 if fragments else 0) + len(marker)
        end = start + len(text)
        offsets.append((start, end, chunk))
        fragments.append(marker + text)
        kept_chunks.append(chunk)
        cursor += len(addition)
    return "\n\n".join(fragments), offsets, kept_chunks


def _select_chunks_node(state: ExtractionGraphState) -> dict[str, Any]:
    """Hybrid chunk selector: full text below threshold, semantic above."""
    threshold = state.get("full_text_threshold_chars", _DEFAULT_FULL_TEXT_THRESHOLD)
    text = state["text"]
    chunks = state.get("chunks") or []
    fallback_reasons = list(state.get("fallback_reasons", []))

    if len(text) <= threshold or not chunks:
        offsets = _build_full_text_offsets(text, chunks)
        return {
            "selected_chunks": list(chunks),
            "selected_text": text,
            "chunk_offsets": offsets,
            "fallback_reasons": [*fallback_reasons, "below_threshold_full_text"],
        }

    schema = state["schema"]
    config = state["config"]
    selected, _query_count, fallback_reason = _select_extraction_chunks(
        chunks,
        schema=schema,
        document_class=state.get("document_class"),
        task_id=config.task_id,
        task_secret=config.task_secret,
    )
    candidate_chunks = selected if selected is not None else chunks
    selected_text, offsets, effective_chunks = _chunks_to_selected_text(
        candidate_chunks,
        max_chars=config.max_chars,
    )
    if fallback_reason:
        fallback_reasons.append(fallback_reason)
    if len(effective_chunks) < len(candidate_chunks):
        fallback_reasons.append("selected_text_truncated_to_max_chars")
    return {
        "selected_chunks": effective_chunks,
        "selected_text": selected_text,
        "chunk_offsets": offsets,
        "fallback_reasons": fallback_reasons,
    }


def _build_full_text_offsets(
    text: str,
    chunks: list[Any],
) -> list[tuple[int, int, Any]]:
    """Build chunk-offset map for a full-text pass by locating each chunk's text."""
    offsets: list[tuple[int, int, Any]] = []
    cursor = 0
    for _index, chunk in enumerate(chunks):
        chunk_text = getattr(chunk, "text", "") or ""
        if not chunk_text:
            continue
        position = text.find(chunk_text, cursor)
        if position < 0:
            position = text.find(chunk_text)
        if position < 0:
            continue
        end = position + len(chunk_text)
        offsets.append((position, end, chunk))
        cursor = end
    return offsets


def _call_llm_streaming(
    *,
    client: Any,
    config: DocumentExtractionProviderConfig,
    system_message: str,
    user_message: str,
    response_format: dict[str, Any],
    max_output_tokens: int | None = None,
) -> tuple[str, str | None]:
    """Issue a streaming chat-completions call and accumulate the full message.

    Streaming keeps the connection actively producing bytes so reverse proxies
    between the worker, the backend, and the model don't enforce read timeouts
    while a long generation is in progress.
    """
    effective_max_tokens = (
        max_output_tokens if max_output_tokens is not None else config.max_output_tokens
    )
    try:
        stream = client.chat.completions.create(
            model=config.model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            response_format=response_format,
            max_tokens=effective_max_tokens,
            temperature=0,
            n=1,
            stream=True,
        )
    except Exception as exc:
        if response_format.get("type") == "json_schema":
            _raise_if_json_schema_unsupported_error(exc)
        raise
    parts: list[str] = []
    finish_reason: str | None = None
    for chunk in stream:
        if isinstance(chunk, dict):
            message = _error_message_from_payload(chunk)
            if (
                response_format.get("type") == "json_schema"
                and message
                and _looks_like_json_schema_unsupported(message)
            ):
                raise JsonSchemaUnsupportedError(message)
            continue
        chunk_error = getattr(chunk, "error", None)
        if isinstance(chunk_error, str):
            if response_format.get(
                "type"
            ) == "json_schema" and _looks_like_json_schema_unsupported(chunk_error):
                raise JsonSchemaUnsupportedError(chunk_error)
            continue
        if isinstance(chunk_error, dict):
            message = _error_message_from_payload({"error": chunk_error})
            if (
                response_format.get("type") == "json_schema"
                and message
                and _looks_like_json_schema_unsupported(message)
            ):
                raise JsonSchemaUnsupportedError(message)
            continue
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        choice = choices[0]
        delta = getattr(choice, "delta", None)
        delta_content = getattr(delta, "content", None) if delta is not None else None
        if isinstance(delta_content, str) and delta_content:
            parts.append(delta_content)
        choice_finish_reason = getattr(choice, "finish_reason", None)
        if isinstance(choice_finish_reason, str) and choice_finish_reason:
            finish_reason = choice_finish_reason
    message = "".join(parts)
    if response_format.get("type") == "json_schema":
        unsupported_message = _json_schema_unsupported_message_from_text(message)
        if unsupported_message:
            raise JsonSchemaUnsupportedError(unsupported_message)
    return message, finish_reason


def _prompt_text_for_batch(
    *,
    state: ExtractionGraphState,
    batch: list[str],
) -> str:
    """Use a narrow evidence window for single repeated-field batches."""
    selected_text = state["selected_text"]
    if len(batch) != 1:
        return selected_text

    schema = state["schema"]
    field = next((item for item in schema.fields if item.name == batch[0]), None)
    if field is None or field.dtype not in {"list", "object_list"}:
        return selected_text
    if not getattr(field, "clustered_under_heading", True):
        return selected_text

    source_chunks = list(state.get("selected_chunks") or state.get("chunks") or [])
    focused_chunks = _focused_repeated_field_chunks(
        chunks=source_chunks,
        field=field,
        boundary_terms=_section_boundary_terms_for_schema(schema),
    )
    if not focused_chunks:
        return selected_text

    focused_text, _offsets, _kept = _chunks_to_selected_text(
        focused_chunks,
        max_chars=state["config"].max_chars,
    )
    if not focused_text.strip():
        return selected_text
    return focused_text


def _extract_pass_node(state: ExtractionGraphState) -> dict[str, Any]:
    """Issue one JSON-mode LLM call per field batch, merging the results."""
    schema = state["schema"]
    config = state["config"]
    target_field_names = state["target_field_names"]
    retry_count = state.get("retry_count", 0)

    retry_hint = None
    if retry_count > 0:
        missing = state.get("missing_required", [])
        if missing:
            retry_hint = (
                "On the previous attempt the following required fields were missing: "
                + ", ".join(missing)
                + ". Look again carefully — the values are likely present in the "
                "SOURCE TEXT but were overlooked."
            )
        batches = _field_batches(schema, target_field_names, missing) or _field_batches(
            schema, target_field_names
        )
    else:
        batches = _field_batches(schema, target_field_names)

    field_records = dict(state.get("field_records", {}))
    raw_outputs = list(state.get("raw_llm_outputs", []))
    fields_by_name = {field.name: field for field in schema.fields}
    batch_parse_errors: list[str] = []

    try:
        client = _build_openai_client(config)
    except Exception as exc:
        logger.warning(
            "Chat extraction client build failed",
            extra={"model": config.model_name, "error": str(exc)},
        )
        return {
            "error": f"chat_llm_failed: {exc}",
            "raw_llm_outputs": raw_outputs,
        }

    for batch_index, batch in enumerate(batches):
        prompt_text = _prompt_text_for_batch(state=state, batch=batch)
        system_message, user_message = _build_prompt(
            schema=schema,
            document_class=state.get("document_class"),
            target_field_names=batch,
            selected_text=prompt_text,
            retry_hint=retry_hint,
        )
        response_format = _json_schema_response_format_for_batch(schema, batch)
        try:
            try:
                message, attempts = _call_llm_with_length_retry(
                    call_llm_streaming=_call_llm_streaming,
                    client=client,
                    config=config,
                    system_message=system_message,
                    user_message=user_message,
                    response_format=response_format,
                    schema_name=schema.name,
                    batch=batch,
                )
            except JsonSchemaUnsupportedError as exc:
                logger.warning(
                    "Chat extraction json_schema response format unsupported; "
                    "retrying with json_object",
                    extra={
                        "model": config.model_name,
                        "schema_name": schema.name,
                        "batch_fields": batch,
                        "error": str(exc),
                    },
                )
                raw_outputs.append(
                    {
                        "pass": retry_count,
                        "batch_index": batch_index,
                        "batch_fields": batch,
                        "finish_reason": None,
                        "content": "",
                        "max_output_tokens": config.max_output_tokens,
                        "response_format_type": "json_schema",
                        "error": str(exc),
                    }
                )
                message, attempts = _call_llm_with_length_retry(
                    call_llm_streaming=_call_llm_streaming,
                    client=client,
                    config=config,
                    system_message=system_message,
                    user_message=user_message,
                    response_format=_JSON_OBJECT_RESPONSE_FORMAT,
                    schema_name=schema.name,
                    batch=batch,
                )
                for attempt in attempts:
                    attempt["response_format_fallback"] = True
                    attempt["fallback_reason"] = "json_schema_unsupported"
            for attempt in attempts:
                raw_outputs.append(
                    {
                        "pass": retry_count,
                        "batch_index": batch_index,
                        "batch_fields": batch,
                        **attempt,
                    }
                )
        except Exception as exc:
            logger.warning(
                "Chat extraction LLM call failed",
                extra={
                    "model": config.model_name,
                    "schema_name": schema.name,
                    "batch_fields": batch,
                    "error": str(exc),
                },
            )
            return {
                "error": f"chat_llm_failed: {exc}",
                "raw_llm_outputs": raw_outputs,
            }
        last_attempt = attempts[-1] if attempts else {}
        parse_log_extra = {
            "model": config.model_name,
            "schema_name": schema.name,
            "batch_fields": batch,
            "response_format_type": last_attempt.get("response_format_type")
            or response_format.get("type"),
            "finish_reason": last_attempt.get("finish_reason"),
            "content_chars": len(message),
            "content_preview": _llm_content_preview(message),
        }
        if not message.strip():
            logger.warning(
                "Chat extraction LLM returned empty content",
                extra=parse_log_extra,
            )
            batch_parse_errors.append(f"batch={batch}: empty assistant content")
            continue
        try:
            parsed = json.loads(message)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Chat extraction LLM returned invalid JSON",
                extra={
                    **parse_log_extra,
                    "error": str(exc),
                },
            )
            batch_parse_errors.append(f"batch={batch}: {exc}")
            continue
        for field_name in batch:
            raw = parsed.get(field_name)
            if raw is None:
                continue
            field = fields_by_name.get(field_name)
            if field is None:
                continue
            records = _records_from_llm_field(field, raw)
            if records:
                field_records[field_name] = records

    error_message = None
    if batch_parse_errors:
        error_message = "chat_invalid_json: " + "; ".join(batch_parse_errors)
    return {
        "field_records": field_records,
        "raw_llm_outputs": raw_outputs,
        "error": error_message,
    }


def _records_from_llm_field(
    field: WorkerDocumentExtractionField,
    raw: Any,
) -> list[dict[str, Any]]:
    """Normalize one LLM-field-output into list-of-record dicts."""
    if field.dtype in {"object_list", "list"}:
        items = raw if isinstance(raw, list) else [raw]
    else:
        items = [raw]
    records: list[dict[str, Any]] = []
    for item in items:
        if field.dtype == "list" and not isinstance(item, dict):
            raw_value = item
            raw_anchor = item if isinstance(item, str) else None
        else:
            if not isinstance(item, dict):
                continue
            raw_value = item.get("value")
            raw_anchor = item.get("evidence_anchor")
            if not isinstance(raw_anchor, str):
                raw_anchor = item.get("evidence_quote")
        if _value_is_empty(raw_value):
            continue
        if field.dtype == "object_list":
            if not isinstance(raw_value, dict):
                continue
            cleaned: Any = {}
            for child in field.fields:
                child_value = _coerce_field_value(
                    raw_value.get(child.name), dtype=child.dtype
                )
                if not _value_is_empty(child_value):
                    cleaned[child.name] = child_value
            if not cleaned:
                continue
        elif field.dtype == "list":
            if isinstance(raw_value, list):
                for nested in raw_value:
                    if _value_is_empty(nested):
                        continue
                    nested_text = str(nested).strip()
                    if nested_text:
                        records.append(
                            {
                                "value": nested_text,
                                "evidence_anchor": _short_anchor(nested_text),
                            }
                        )
                continue
            cleaned = str(raw_value).strip()
            if not cleaned:
                continue
        else:
            cleaned = _coerce_field_value(raw_value, dtype=field.dtype)
            if _value_is_empty(cleaned):
                continue
        records.append(
            {
                "value": cleaned,
                "evidence_anchor": _short_anchor(raw_anchor)
                if isinstance(raw_anchor, str)
                else None,
            }
        )
    return records


def _ground_evidence_node(state: ExtractionGraphState) -> dict[str, Any]:
    """Substring-match each evidence_quote to derive WorkerDocumentEvidence."""
    selected_text = state.get("selected_text", "")
    chunk_offsets = state.get("chunk_offsets", [])
    field_records = state.get("field_records", {})
    grounded: dict[str, list[dict[str, Any]]] = {}
    for field_name, records in field_records.items():
        grounded_records: list[dict[str, Any]] = []
        for record in records:
            anchor = record.get("evidence_anchor")
            evidence, snippet = _ground_anchor(anchor, selected_text, chunk_offsets)
            grounded_records.append(
                {
                    "value": record["value"],
                    "evidence_anchor": anchor,
                    "evidence": evidence,
                    "snippet": snippet,
                }
            )
        grounded[field_name] = grounded_records
    return {"field_records": grounded}


def _check_completeness_node(state: ExtractionGraphState) -> dict[str, Any]:
    """Compute missing required fields."""
    schema = state["schema"]
    target_field_names = state["target_field_names"]
    field_records = state.get("field_records", {})
    missing_required = [
        field.name
        for field in schema.fields
        if field.name in target_field_names
        and field.required
        and not field_records.get(field.name)
    ]
    return {"missing_required": missing_required}


def _should_retry(state: ExtractionGraphState) -> str:
    missing = state.get("missing_required", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", _DEFAULT_MAX_RETRIES)
    if missing and retry_count < max_retries:
        return "refine"
    return "validate"


def _refine_and_retry_node(state: ExtractionGraphState) -> dict[str, Any]:
    """Increment retry counter; on pass 2 also re-query chunks for missing fields."""
    retry_count = state.get("retry_count", 0) + 1
    updates: dict[str, Any] = {"retry_count": retry_count}
    if retry_count >= 2 and state.get("chunks"):
        config = state["config"]
        schema = state["schema"]
        missing = state.get("missing_required", [])
        selected, _query_count, fallback_reason = _select_extraction_chunks(
            state.get("chunks"),
            schema=schema,
            document_class=state.get("document_class"),
            task_id=config.task_id,
            task_secret=config.task_secret,
        )
        if selected:
            existing_indices = {
                _chunk_index_from_chunk(c, idx)
                for idx, c in enumerate(state.get("selected_chunks", []))
            }
            extra = [
                chunk
                for idx, chunk in enumerate(selected)
                if _chunk_index_from_chunk(chunk, idx) not in existing_indices
            ]
            if extra:
                logger.info(
                    "Chat extraction retry pulling in extra chunks for missing fields",
                    extra={
                        "schema_name": schema.name,
                        "missing_fields": missing,
                        "extra_chunk_count": len(extra),
                    },
                )
                combined_chunks = list(state.get("selected_chunks", [])) + extra
                selected_text, offsets, kept_chunks = _chunks_to_selected_text(
                    combined_chunks,
                    max_chars=config.max_chars,
                )
                updates["selected_chunks"] = kept_chunks
                updates["selected_text"] = selected_text
                updates["chunk_offsets"] = offsets
        if fallback_reason:
            fallback_reasons = list(state.get("fallback_reasons", []))
            fallback_reasons.append(f"retry:{fallback_reason}")
            updates["fallback_reasons"] = fallback_reasons
    return updates


def _validate_node(_state: ExtractionGraphState) -> dict[str, Any]:
    """Final validation; nothing to mutate. Acts as a graph terminal sentinel."""
    return {}


def _build_extraction_graph():
    graph = StateGraph(ExtractionGraphState)
    graph.add_node("select_chunks", _select_chunks_node)
    graph.add_node("extract_pass", _extract_pass_node)
    graph.add_node("ground_evidence", _ground_evidence_node)
    graph.add_node("check_completeness", _check_completeness_node)
    graph.add_node("refine_and_retry", _refine_and_retry_node)
    graph.add_node("validate", _validate_node)
    graph.add_edge(START, "select_chunks")
    graph.add_edge("select_chunks", "extract_pass")
    graph.add_edge("extract_pass", "ground_evidence")
    graph.add_edge("ground_evidence", "check_completeness")
    graph.add_conditional_edges(
        "check_completeness",
        _should_retry,
        {"refine": "refine_and_retry", "validate": "validate"},
    )
    graph.add_edge("refine_and_retry", "extract_pass")
    graph.add_edge("validate", END)
    return graph.compile()


_EXTRACTION_GRAPH = _build_extraction_graph()


def _result_from_state(
    state: ExtractionGraphState,
    *,
    provider_name: str,
    model_name: str,
    schema: WorkerDocumentExtractionSchema,
    document_class: str | None,
    document_class_id: str | None,
    target_field_names: list[str],
) -> WorkerDocumentExtractionResult:
    """Assemble the normalized worker result from final graph state."""
    field_records = state.get("field_records", {})
    evidence_required = state.get("evidence_required", True)

    field_results: dict[str, WorkerDocumentExtractionFieldResult] = {}
    data: dict[str, Any] = {}
    missing_required_fields: list[str] = []
    invalid_fields: list[str] = []
    fields_without_evidence: list[str] = []
    fields_with_evidence = 0

    for field in schema.fields:
        if field.name not in target_field_names:
            continue
        records = field_records.get(field.name, [])
        if not records:
            if field.required:
                missing_required_fields.append(field.name)
            field_results[field.name] = WorkerDocumentExtractionFieldResult(
                value=[] if field.dtype in {"object_list", "list"} else None,
                dtype=field.dtype,
                required=field.required,
                missing_reason="missing_required" if field.required else "not_found",
            )
            if field.dtype in {"object_list", "list"}:
                data[field.name] = []
            continue

        if field.dtype in {"object_list", "list"}:
            value: Any = [record["value"] for record in records]
        else:
            value = records[0]["value"]

        validation_errors = _field_validation_errors(value, dtype=field.dtype)
        evidence: list[WorkerDocumentEvidence] = []
        item_evidence: list[list[WorkerDocumentEvidence]] = []
        for record in records:
            record_evidence = list(record.get("evidence", []) or [])[
                :MAX_FIELD_EVIDENCE
            ]
            if field.dtype in {"object_list", "list"}:
                item_evidence.append(record_evidence)
            for item in record_evidence:
                if item not in evidence:
                    evidence.append(item)
        evidence = evidence[:MAX_FIELD_EVIDENCE]

        record_validation_errors = list(validation_errors)
        items_without_evidence = sum(
            1 for record in records if not record.get("evidence")
        )
        if evidence_required and items_without_evidence:
            record_validation_errors.append("evidence_anchor_not_found")

        if record_validation_errors:
            invalid_fields.append(field.name)

        if evidence:
            fields_with_evidence += 1
        else:
            fields_without_evidence.append(field.name)

        candidates = [
            _candidate_payload(
                value=record["value"],
                confidence=None,
                evidence=record.get("evidence", []) or [],
                span=None,
            )
            for record in records
        ]

        field_results[field.name] = WorkerDocumentExtractionFieldResult(
            value=value,
            dtype=field.dtype,
            required=field.required,
            evidence=evidence,
            item_evidence=item_evidence,
            candidate_values=candidates,
            validation_errors=record_validation_errors,
            items_without_evidence=items_without_evidence,
        )
        data[field.name] = value

    summary = WorkerDocumentExtractionSummary(
        missing_required_fields=missing_required_fields,
        invalid_fields=invalid_fields,
        fields_without_evidence=fields_without_evidence,
        fields_with_evidence=fields_with_evidence,
        needs_review=bool(
            missing_required_fields or invalid_fields or fields_without_evidence
        ),
    )

    fallback_reasons = state.get("fallback_reasons", []) or []
    raw_output = {
        "selected_chunk_count": len(state.get("selected_chunks", []) or []),
        "selected_chars": len(state.get("selected_text", "") or ""),
        "retry_count": state.get("retry_count", 0),
        "fallback_reasons": fallback_reasons,
        "raw_llm_outputs": state.get("raw_llm_outputs", []),
        "evidence_required": evidence_required,
    }
    if state.get("error"):
        raw_output["error"] = state["error"]

    return WorkerDocumentExtractionResult(
        status="completed",
        provider=provider_name,
        model=model_name,
        schema_id=schema.id or None,
        schema_name=schema.name,
        schema_version=schema.version,
        document_class_id=document_class_id or schema.document_class_id or None,
        document_class=document_class or schema.document_class,
        data=data,
        fields=field_results,
        summary=summary,
        raw_output=raw_output,
    )


def _failed_result(
    *,
    provider_name: str,
    model_name: str,
    schema: WorkerDocumentExtractionSchema,
    document_class: str | None,
    document_class_id: str | None,
    error: str,
    target_field_names: list[str],
) -> WorkerDocumentExtractionResult:
    field_results = {}
    data: dict[str, Any] = {}
    for field in schema.fields:
        if field.name not in target_field_names:
            continue
        field_results[field.name] = WorkerDocumentExtractionFieldResult(
            value=[] if field.dtype in {"object_list", "list"} else None,
            dtype=field.dtype,
            required=field.required,
            validation_errors=["provider_failed"],
            missing_reason="missing_required" if field.required else "not_found",
        )
        if field.dtype in {"object_list", "list"}:
            data[field.name] = []
    return WorkerDocumentExtractionResult(
        status="failed",
        provider=provider_name,
        model=model_name,
        schema_id=schema.id or None,
        schema_name=schema.name,
        schema_version=schema.version,
        document_class_id=document_class_id or schema.document_class_id or None,
        document_class=document_class or schema.document_class,
        data=data,
        fields=field_results,
        summary=WorkerDocumentExtractionSummary(
            missing_required_fields=[
                field.name
                for field in schema.fields
                if field.name in target_field_names and field.required
            ],
            invalid_fields=list(field_results.keys()),
            needs_review=True,
        ),
        error=error,
    )


def _extract_document_data_langgraph(
    text: str,
    *,
    schema: WorkerDocumentExtractionSchema,
    document_class: str | None,
    document_class_id: str | None,
    chunks: list[Any] | None,
    config: DocumentExtractionProviderConfig,
) -> WorkerDocumentExtractionResult:
    """Entry point for the LangGraph-backed chat extraction provider."""
    target_field_names = [field.name for field in schema.fields]
    if not target_field_names:
        return WorkerDocumentExtractionResult(
            status="skipped",
            provider=config.provider,
            model=config.model_name,
            schema_id=schema.id or None,
            schema_name=schema.name,
            schema_version=schema.version,
            document_class_id=document_class_id or schema.document_class_id or None,
            document_class=document_class or schema.document_class,
            error="No fields configured for chat extraction",
        )

    normalized = _normalize_text(text, max_chars=config.max_chars)
    if not normalized:
        return WorkerDocumentExtractionResult(
            status="skipped",
            provider=config.provider,
            model=config.model_name,
            schema_id=schema.id or None,
            schema_name=schema.name,
            schema_version=schema.version,
            document_class_id=document_class_id or schema.document_class_id or None,
            document_class=document_class or schema.document_class,
            error="Document text was empty after normalization",
        )

    max_retries, evidence_required, threshold = _runtime_settings(config)

    initial_state: ExtractionGraphState = {
        "text": normalized,
        "chunks": chunks,
        "schema": schema,
        "document_class": document_class,
        "document_class_id": document_class_id,
        "config": config,
        "target_field_names": target_field_names,
        "selected_chunks": [],
        "selected_text": "",
        "chunk_offsets": [],
        "field_records": {},
        "missing_required": [],
        "retry_count": 0,
        "fallback_reasons": [],
        "raw_llm_outputs": [],
        "error": None,
        "max_retries": max_retries,
        "evidence_required": evidence_required,
        "full_text_threshold_chars": min(threshold, config.max_chars),
    }

    logger.info(
        "Chat extraction starting",
        extra={
            "provider": config.provider,
            "model": config.model_name,
            "schema_id": schema.id or None,
            "schema_name": schema.name,
            "field_count": len(target_field_names),
            "max_retries": max_retries,
            "evidence_required": evidence_required,
            "full_text_threshold_chars": initial_state["full_text_threshold_chars"],
            "text_chars": len(normalized),
            "chunk_count": len(chunks or []),
        },
    )

    try:
        final_state = _EXTRACTION_GRAPH.invoke(initial_state)
    except Exception as exc:
        logger.warning(
            "Chat extraction graph failed",
            extra={"schema_name": schema.name, "error": str(exc)},
        )
        return _failed_result(
            provider_name=config.provider,
            model_name=config.model_name,
            schema=schema,
            document_class=document_class,
            document_class_id=document_class_id,
            error=f"chat_graph_failed: {exc}",
            target_field_names=target_field_names,
        )

    if final_state.get("error"):
        return _failed_result(
            provider_name=config.provider,
            model_name=config.model_name,
            schema=schema,
            document_class=document_class,
            document_class_id=document_class_id,
            error=final_state["error"],
            target_field_names=target_field_names,
        )

    return _result_from_state(
        final_state,
        provider_name=config.provider,
        model_name=config.model_name,
        schema=schema,
        document_class=document_class,
        document_class_id=document_class_id,
        target_field_names=target_field_names,
    )


class LangGraphExtractionProvider:
    """Chat-style structured extraction with quote-grounded evidence."""

    key = LANGGRAPH_PROVIDER

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
        return _extract_document_data_langgraph(
            text,
            schema=schema,
            document_class=document_class,
            document_class_id=document_class_id,
            chunks=chunks,
            config=config,
        )
