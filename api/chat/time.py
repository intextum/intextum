"""Shared timestamp helpers for chat state and transcript shaping."""

from datetime import datetime, timezone


def iso_now() -> str:
    """Return an ISO timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()
