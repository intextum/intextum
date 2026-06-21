"""Valkey-backed event storage for resumable chat run replay."""

from __future__ import annotations

import json
from typing import Any

from chat.stream import jsonable_stream_data
from config import get_settings
from models.chat.runs import ChatRunEvent


def _decode_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


class ChatRunEventStore:
    """Append and replay resumable chat run events from Valkey Streams."""

    def __init__(self, client: Any, *, ttl_seconds: int | None = None):
        self.client = client
        self.ttl_seconds = (
            get_settings().CHAT_RUN_EVENT_TTL_SECONDS
            if ttl_seconds is None
            else ttl_seconds
        )

    @staticmethod
    def stream_key(run_id: str) -> str:
        """Return the Valkey stream key for one run."""
        return f"chat:run:{run_id}:events"

    @staticmethod
    def _serialize_payload(payload: Any) -> str:
        return json.dumps(jsonable_stream_data(payload), ensure_ascii=False)

    @staticmethod
    def _deserialize_payload(payload: Any) -> Any:
        raw_payload = _decode_value(payload)
        if not isinstance(raw_payload, str):
            return raw_payload
        return json.loads(raw_payload)

    @staticmethod
    def _normalized_fields(fields: dict[str, Any]) -> dict[str, Any]:
        return {
            str(_decode_value(key)): _decode_value(value)
            for key, value in fields.items()
        }

    @staticmethod
    def _row_to_event(
        run_id: str,
        entry_id: str,
        fields: dict[str, Any],
    ) -> ChatRunEvent:
        normalized_fields = ChatRunEventStore._normalized_fields(fields)
        return ChatRunEvent(
            event=str(normalized_fields["event"]),
            payload=ChatRunEventStore._deserialize_payload(
                normalized_fields.get("payload", "null")
            ),
            run_id=run_id,
            conversation_id=str(normalized_fields["conversation_id"]),
            event_id=entry_id,
            created_at=(
                str(normalized_fields["created_at"])
                if normalized_fields.get("created_at") is not None
                else None
            ),
        )

    async def append_event(
        self,
        *,
        run_id: str,
        conversation_id: str,
        event: str,
        payload: Any = None,
        created_at: str | None = None,
    ) -> ChatRunEvent:
        """Append one stream event and return the persisted event metadata."""
        fields = {
            "event": event,
            "payload": self._serialize_payload(payload),
            "conversation_id": conversation_id,
        }
        if created_at is not None:
            fields["created_at"] = created_at

        entry_id = await self.client.xadd(self.stream_key(run_id), fields)
        if self.ttl_seconds > 0:
            await self.client.expire(self.stream_key(run_id), self.ttl_seconds)

        return ChatRunEvent(
            event=event,
            payload=payload,
            run_id=run_id,
            conversation_id=conversation_id,
            event_id=str(_decode_value(entry_id)),
            created_at=created_at,
        )

    async def replay_events(
        self,
        *,
        run_id: str,
        after_id: str | None = None,
        limit: int | None = None,
    ) -> list[ChatRunEvent]:
        """Return stored events after the supplied event id."""
        start = f"({after_id}" if after_id else "-"
        raw_entries = await self.client.xrange(
            self.stream_key(run_id),
            min=start,
            max="+",
            count=limit or get_settings().CHAT_RUN_MAX_REPLAY_EVENTS,
        )
        return [
            self._row_to_event(
                run_id,
                str(_decode_value(entry_id)),
                fields,
            )
            for entry_id, fields in raw_entries
        ]

    async def read_next_events(
        self,
        *,
        run_id: str,
        after_id: str | None,
        block_ms: int = 1000,
        count: int = 100,
    ) -> list[ChatRunEvent]:
        """Read the next available event batch after the supplied id."""
        stream_id = after_id or "0-0"
        raw_streams = await self.client.xread(
            {self.stream_key(run_id): stream_id},
            block=block_ms,
            count=count,
        )
        if not raw_streams:
            return []

        stream_entries = raw_streams[0][1]
        return [
            self._row_to_event(
                run_id,
                str(_decode_value(entry_id)),
                fields,
            )
            for entry_id, fields in stream_entries
        ]
