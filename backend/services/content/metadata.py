"""Small helpers for normalizing content metadata values."""

from __future__ import annotations


def metadata_float(
    metadata: dict[str, object], key: str, default: float = 0.0
) -> float:
    value = metadata.get(key, default)
    return float(value) if isinstance(value, (int, float, str)) else default


def metadata_int(metadata: dict[str, object], key: str, default: int = 0) -> int:
    value = metadata.get(key, default)
    return int(value) if isinstance(value, (int, float, str)) else default
