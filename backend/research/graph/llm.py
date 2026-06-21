"""LLM response parsing and schema invocation helpers for the research graph."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from services.ai_limits import (
    DEFAULT_CHAT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_CHAT_TIMEOUT_SECONDS,
    run_ai_call,
)

_CODE_FENCE_PATTERN = re.compile(r"^```(?:[a-zA-Z0-9_-]+)?\s*")
_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _response_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    return ""


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    stripped = _CODE_FENCE_PATTERN.sub("", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = _strip_code_fences(text)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = _JSON_OBJECT_PATTERN.search(stripped)
    if not match:
        raise ValueError("Model response did not contain a JSON object")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Model response did not contain a JSON object")
    return parsed


def _coerce_single_string_field_schema(
    schema: type[BaseModel],
    response_text: str,
) -> BaseModel | None:
    model_fields = getattr(schema, "model_fields", {})
    if len(model_fields) != 1:
        return None

    field_name, field_info = next(iter(model_fields.items()))
    if field_info.annotation is not str:
        return None

    stripped = _strip_code_fences(response_text)
    if not stripped:
        return None

    try:
        return schema.model_validate({field_name: stripped})
    except ValidationError:
        return None


async def _invoke_json_schema(
    *,
    runtime,
    schema: type[BaseModel],
    system_prompt: str,
    user_prompt: str,
    model_builder: Callable[[Any], Any],
) -> BaseModel:
    model = model_builder(runtime)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    response = await run_ai_call(
        lambda: model.ainvoke(messages),
        settings=runtime.settings,
        name="chat",
        timeout_attr="CHAT_TIMEOUT_SECONDS",
        default_timeout_seconds=DEFAULT_CHAT_TIMEOUT_SECONDS,
        concurrency_attr="CHAT_MAX_CONCURRENT_REQUESTS",
        default_concurrency=DEFAULT_CHAT_MAX_CONCURRENT_REQUESTS,
        timeout_detail="Chat model request timed out",
        busy_detail="Chat model is busy",
    )
    response_text = _response_text(response)
    try:
        return schema.model_validate(_extract_json_object(response_text))
    except (ValidationError, ValueError) as exc:
        fallback = _coerce_single_string_field_schema(schema, response_text)
        if fallback is not None:
            return fallback
        raise RuntimeError(f"Invalid structured model response: {exc}") from exc
