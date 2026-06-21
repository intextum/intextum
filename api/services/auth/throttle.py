"""Valkey-backed local login throttling."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from config import get_settings
from services.valkey import get_valkey_client, init_valkey_client


@dataclass(frozen=True)
class LoginThrottleState:
    """Current login throttle decision."""

    allowed: bool
    retry_after_seconds: int | None = None


class LocalLoginThrottle:
    """Track failed local login attempts by username/email and client IP."""

    KEY_PREFIX = "auth:login:"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def _client(self) -> Any | None:
        if not bool(getattr(self.settings, "AUTH_LOGIN_THROTTLE_ENABLED", True)):
            return None
        client = get_valkey_client()
        if client is None:
            client = await init_valkey_client()
        if client is None:
            raise RuntimeError("Valkey is required for local login throttling")
        return client

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _subject(cls, kind: str, value: str) -> str:
        normalized = value.strip().lower()
        return f"{kind}:{cls._hash(normalized)}"

    @classmethod
    def _counter_key(cls, subject: str) -> str:
        return f"{cls.KEY_PREFIX}fail:{subject}"

    @classmethod
    def _lock_key(cls, subject: str) -> str:
        return f"{cls.KEY_PREFIX}lock:{subject}"

    def _subjects(self, *, identifier: str, client_ip: str) -> list[str]:
        subjects = [self._subject("id", identifier)]
        if client_ip.strip():
            subjects.append(self._subject("ip", client_ip))
        return subjects

    async def _retry_after(self, client: Any, lock_keys: list[str]) -> int:
        retry_after = 0
        for key in lock_keys:
            ttl = int(await client.ttl(key))
            if ttl > retry_after:
                retry_after = ttl
        return max(1, retry_after)

    async def check_allowed(
        self,
        *,
        identifier: str,
        client_ip: str,
    ) -> LoginThrottleState:
        """Return whether a local login attempt may proceed."""
        client = await self._client()
        if client is None:
            return LoginThrottleState(allowed=True)

        lock_keys = [
            self._lock_key(subject)
            for subject in self._subjects(identifier=identifier, client_ip=client_ip)
        ]
        if not lock_keys:
            return LoginThrottleState(allowed=True)
        lock_count = await client.exists(*lock_keys)
        if int(lock_count or 0) <= 0:
            return LoginThrottleState(allowed=True)
        return LoginThrottleState(
            allowed=False,
            retry_after_seconds=await self._retry_after(client, lock_keys),
        )

    async def record_failure(
        self,
        *,
        identifier: str,
        client_ip: str,
    ) -> LoginThrottleState:
        """Record a failed login and return the resulting throttle state."""
        client = await self._client()
        if client is None:
            return LoginThrottleState(allowed=True)

        max_attempts = max(1, int(self.settings.AUTH_LOGIN_MAX_ATTEMPTS))
        window_seconds = max(1, int(self.settings.AUTH_LOGIN_WINDOW_SECONDS))
        lockout_seconds = max(1, int(self.settings.AUTH_LOGIN_LOCKOUT_SECONDS))
        subjects = self._subjects(identifier=identifier, client_ip=client_ip)
        locked_keys: list[str] = []

        for subject in subjects:
            counter_key = self._counter_key(subject)
            count = int(await client.incr(counter_key))
            if count == 1:
                await client.expire(counter_key, window_seconds)
            if count >= max_attempts:
                lock_key = self._lock_key(subject)
                await client.set(lock_key, "1", ex=lockout_seconds)
                locked_keys.append(lock_key)

        if not locked_keys:
            return LoginThrottleState(allowed=True)
        return LoginThrottleState(
            allowed=False,
            retry_after_seconds=await self._retry_after(client, locked_keys),
        )

    async def clear(self, *, identifier: str, client_ip: str) -> None:
        """Clear throttle state after a successful local login."""
        client = await self._client()
        if client is None:
            return

        keys: list[str] = []
        for subject in self._subjects(identifier=identifier, client_ip=client_ip):
            keys.extend([self._counter_key(subject), self._lock_key(subject)])
        if keys:
            await client.delete(*keys)
