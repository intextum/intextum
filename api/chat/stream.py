"""Generic SSE helpers for the chat stream endpoint."""

import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage, message_to_dict

SSE_CONTENT_TYPE = "text/event-stream"
STREAM_RESPONSE_HEADERS = {
    "X-Accel-Buffering": "no",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}


def _serialize_langchain_message(message: BaseMessage) -> dict[str, Any]:
    """Flatten LangChain messages/chunks into the dict shape the JS client expects."""
    serialized = message_to_dict(message)
    payload = serialized.get("data")
    if not isinstance(payload, dict):
        return {"type": serialized.get("type"), "data": payload}

    flat_payload = dict(payload)
    flat_payload["type"] = serialized.get("type", flat_payload.get("type"))
    return flat_payload


def jsonable_stream_data(data: Any) -> Any:
    """Convert LangGraph stream payloads into JSON-safe structures."""
    return jsonable_encoder(
        data,
        custom_encoder={BaseMessage: _serialize_langchain_message},
    )


def encode_sse_event(event: str, data: Any, event_id: str | None = None) -> str:
    """Encode one SSE event frame."""
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(jsonable_stream_data(data), ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def build_streaming_response(frame_iter: Any) -> StreamingResponse:
    """Create a streaming response for SSE clients."""
    return StreamingResponse(
        frame_iter,
        media_type=SSE_CONTENT_TYPE,
        headers=STREAM_RESPONSE_HEADERS,
    )
