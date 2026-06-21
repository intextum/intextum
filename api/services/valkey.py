"""Helpers for optional shared Valkey access."""

from __future__ import annotations

from typing import Any

from config import get_settings

try:
    from valkey.asyncio import Valkey as AsyncValkey
except ImportError:  # pragma: no cover - exercised only without dependency installed
    AsyncValkey = None

_valkey_client: Any | None = None


def is_valkey_configured() -> bool:
    """Return whether runtime configuration points at a Valkey instance."""
    return bool(get_settings().VALKEY_URL.strip())


async def init_valkey_client() -> Any | None:
    """Initialize the shared async Valkey client when configuration is present."""
    global _valkey_client

    if _valkey_client is not None:
        return _valkey_client

    url = get_settings().VALKEY_URL.strip()
    if not url:
        return None

    if AsyncValkey is None:
        raise RuntimeError(
            "Valkey support requires the 'valkey' Python package to be installed"
        )

    _valkey_client = AsyncValkey.from_url(url, decode_responses=True)
    return _valkey_client


def get_valkey_client() -> Any | None:
    """Return the initialized shared async Valkey client, if any."""
    return _valkey_client


async def probe_valkey(client: Any | None = None) -> bool:
    """Return whether the configured Valkey instance responds to PING."""
    resolved_client = client if client is not None else await init_valkey_client()
    if resolved_client is None:
        return False

    result = await resolved_client.ping()
    return bool(result)


async def close_valkey_client() -> None:
    """Close the shared async Valkey client if it was initialized."""
    global _valkey_client

    if _valkey_client is None:
        return

    await _valkey_client.aclose()

    _valkey_client = None
