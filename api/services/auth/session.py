"""Local-auth Valkey-backed session helpers."""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from config import get_settings
from services.valkey import get_valkey_client, init_valkey_client

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class SessionRecord:
    session_id: str
    user_sub: str
    auth_provider: str
    csrf_token: str
    session_version: int
    issued_at: datetime
    last_seen_at: datetime
    absolute_expires_at: datetime


class LocalSessionService:
    """Opaque session storage in Valkey."""

    KEY_PREFIX = "auth:session:"

    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{LocalSessionService.KEY_PREFIX}{session_id}"

    async def _client(self) -> Any:
        client = get_valkey_client()
        if client is None:
            client = await init_valkey_client()
        if client is None:
            raise RuntimeError("Valkey is required for local auth sessions")
        return client

    def _serialize(self, record: SessionRecord) -> str:
        return json.dumps(
            {
                "session_id": record.session_id,
                "user_sub": record.user_sub,
                "auth_provider": record.auth_provider,
                "csrf_token": record.csrf_token,
                "session_version": record.session_version,
                "issued_at": _isoformat(record.issued_at),
                "last_seen_at": _isoformat(record.last_seen_at),
                "absolute_expires_at": _isoformat(record.absolute_expires_at),
            }
        )

    def _deserialize(self, payload: str) -> SessionRecord:
        raw = json.loads(payload)
        return SessionRecord(
            session_id=raw["session_id"],
            user_sub=raw["user_sub"],
            auth_provider=raw["auth_provider"],
            csrf_token=raw["csrf_token"],
            session_version=int(raw["session_version"]),
            issued_at=_parse_datetime(raw["issued_at"]),
            last_seen_at=_parse_datetime(raw["last_seen_at"]),
            absolute_expires_at=_parse_datetime(raw["absolute_expires_at"]),
        )

    async def create_session(
        self,
        *,
        user_sub: str,
        session_version: int,
        auth_provider: str = "local",
    ) -> SessionRecord:
        now = _utcnow()
        record = SessionRecord(
            session_id=secrets.token_urlsafe(32),
            user_sub=user_sub,
            auth_provider=auth_provider,
            csrf_token=secrets.token_urlsafe(24),
            session_version=session_version,
            issued_at=now,
            last_seen_at=now,
            absolute_expires_at=now
            + timedelta(seconds=self.settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS),
        )
        client = await self._client()
        await client.set(
            self._key(record.session_id),
            self._serialize(record),
            ex=self.settings.AUTH_SESSION_IDLE_TTL_SECONDS,
        )
        return record

    async def get_session(self, session_id: str) -> SessionRecord | None:
        if not session_id:
            return None
        client = await self._client()
        key = self._key(session_id)
        payload = await client.get(key)
        if not payload:
            return None
        try:
            record = self._deserialize(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "Dropping invalid local auth session %s: %s", session_id, exc
            )
            await client.delete(key)
            return None
        now = _utcnow()
        if record.absolute_expires_at <= now:
            await client.delete(key)
            return None
        record.last_seen_at = now
        await client.set(
            key,
            self._serialize(record),
            ex=self.settings.AUTH_SESSION_IDLE_TTL_SECONDS,
        )
        return record

    async def revoke_session(self, session_id: str) -> None:
        if not session_id:
            return
        client = await self._client()
        await client.delete(self._key(session_id))
