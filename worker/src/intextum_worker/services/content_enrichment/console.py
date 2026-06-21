"""Small logging helpers for content enrichment providers."""

from __future__ import annotations

import json
from typing import Any

EXTRACTION_CONSOLE_TEXT_CHARS = 8_000
EXTRACTION_CONSOLE_JSON_CHARS = 8_000


def _clip_console_text(value: str, *, max_chars: int) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    return value[:max_chars].rstrip(), True


def _console_json(value: Any, *, max_chars: int) -> tuple[str, bool]:
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        serialized = repr(value)
    return _clip_console_text(serialized, max_chars=max_chars)
