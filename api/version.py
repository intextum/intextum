"""Shared application version resolution.

The canonical version lives in the repository-root ``VERSION`` file. At runtime
the ``APP_VERSION`` environment variable (set by docker-compose) takes
precedence so all components report the same number without rebuilding.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_FALLBACK_VERSION = "0.0.0"


def _read_version_file() -> str | None:
    """Return the version from the nearest ``VERSION`` file, if any."""
    for directory in (
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
    ):
        candidate = directory / "VERSION"
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8").strip()
            if text:
                return text
    return None


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """Resolve the application version (env override → VERSION file → fallback)."""
    env_value = os.environ.get("APP_VERSION", "").strip()
    if env_value:
        return env_value
    return _read_version_file() or _FALLBACK_VERSION
