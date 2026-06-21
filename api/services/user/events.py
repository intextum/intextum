"""Valkey-backed user-scoped lifecycle event helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from config import get_settings
from models.user import UserEventRecord
from services.valkey import init_valkey_client, is_valkey_configured

logger = logging.getLogger(__name__)


def _decode_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _decode_metadata(value: Any, *, entry_id: str) -> dict[str, Any]:
    if value is None:
        return {}

    try:
        metadata = json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Ignoring invalid user event metadata for entry %s", entry_id)
        return {}

    if not isinstance(metadata, dict):
        logger.warning("Ignoring non-object user event metadata for entry %s", entry_id)
        return {}

    return metadata


class UserEventStore:
    """Append and replay user-scoped lifecycle events from Valkey Streams."""

    def __init__(self, client: Any, *, ttl_seconds: int | None = None):
        self.client = client
        self.ttl_seconds = (
            get_settings().USER_EVENT_TTL_SECONDS
            if ttl_seconds is None
            else ttl_seconds
        )

    @staticmethod
    def stream_key(user_sub: str) -> str:
        """Return the Valkey stream key for one user's lifecycle events."""
        return f"user:{user_sub}:events"

    @staticmethod
    def _row_to_event(entry_id: str, fields: dict[str, Any]) -> UserEventRecord:
        normalized_fields = {
            str(_decode_value(key)): _decode_value(value)
            for key, value in fields.items()
        }
        return UserEventRecord.model_validate(
            {
                "kind": normalized_fields["kind"],
                "resource_type": normalized_fields["resource_type"],
                "resource_id": normalized_fields["resource_id"],
                "status": normalized_fields["status"],
                "metadata": _decode_metadata(
                    normalized_fields.get("metadata"),
                    entry_id=entry_id,
                ),
                "created_at": normalized_fields["created_at"],
                "event_id": entry_id,
            }
        )

    async def append_event(
        self,
        *,
        user_sub: str,
        event: UserEventRecord,
    ) -> UserEventRecord:
        """Append one user event and return the stored metadata."""
        fields = {
            "kind": event.kind,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "status": event.status,
            "metadata": json.dumps(event.metadata, ensure_ascii=False),
            "created_at": event.created_at,
        }
        entry_id = await self.client.xadd(self.stream_key(user_sub), fields)
        if self.ttl_seconds > 0:
            await self.client.expire(self.stream_key(user_sub), self.ttl_seconds)

        return event.model_copy(update={"event_id": str(_decode_value(entry_id))})

    async def replay_events(
        self,
        *,
        user_sub: str,
        after_id: str | None = None,
        limit: int | None = None,
    ) -> list[UserEventRecord]:
        """Return stored user events after the supplied event id."""
        start = f"({after_id}" if after_id else "-"
        raw_entries = await self.client.xrange(
            self.stream_key(user_sub),
            min=start,
            max="+",
            count=limit or get_settings().USER_EVENT_MAX_REPLAY_EVENTS,
        )
        return [
            self._row_to_event(str(_decode_value(entry_id)), fields)
            for entry_id, fields in raw_entries
        ]

    async def read_next_events(
        self,
        *,
        user_sub: str,
        after_id: str | None,
        block_ms: int = 1000,
        count: int = 100,
    ) -> list[UserEventRecord]:
        """Read the next available batch of user events."""
        stream_id = after_id or "0-0"
        raw_streams = await self.client.xread(
            {self.stream_key(user_sub): stream_id},
            block=block_ms,
            count=count,
        )
        if not raw_streams:
            return []

        stream_entries = raw_streams[0][1]
        return [
            self._row_to_event(str(_decode_value(entry_id)), fields)
            for entry_id, fields in stream_entries
        ]


async def publish_user_event(
    *,
    user_sub: str | None,
    event: UserEventRecord,
) -> UserEventRecord | None:
    """Persist one user event when Valkey-backed events are configured."""
    if not user_sub or not is_valkey_configured():
        return None

    client = await init_valkey_client()
    if client is None:
        return None

    try:
        return await UserEventStore(client).append_event(user_sub=user_sub, event=event)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to publish user event %s for %s: %s",
            event.kind,
            user_sub,
            exc,
            exc_info=True,
        )
        return None
