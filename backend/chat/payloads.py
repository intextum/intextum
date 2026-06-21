"""Small coercion helpers for chat payload metadata."""

from datetime import datetime
from typing import Any


def string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, int)]


def datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
