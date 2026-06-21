"""Content-enrichment registry model reference helpers."""

from __future__ import annotations

_REGISTRY_MODEL_PREFIX = "registry:"


def content_enrichment_registry_model_ref(model_id: str) -> str:
    """Return the persisted AI settings value for one registry-backed model."""
    return f"{_REGISTRY_MODEL_PREFIX}{model_id}"


def parse_content_enrichment_registry_model_ref(model_name: str | None) -> str | None:
    """Return the registry model id when the setting points to one registry entry."""
    if not isinstance(model_name, str):
        return None
    normalized = model_name.strip()
    if not normalized.startswith(_REGISTRY_MODEL_PREFIX):
        return None
    model_id = normalized[len(_REGISTRY_MODEL_PREFIX) :].strip()
    return model_id or None
