"""Model loading and local registry artifact handling for content enrichment."""

from __future__ import annotations

import json
import shutil
import tarfile
from pathlib import Path

from intextum_worker.config import get_settings
from intextum_worker.services.api_client import ApiClient

_REGISTRY_MODEL_PREFIX = "registry:"
_EXTRACTOR_CACHE_MAX_SIZE = 4
_EXTRACTOR_CACHE: dict[str, object] = {}


def _load_gliner2_class():
    try:
        from gliner2 import GLiNER2
    except ImportError as exc:  # pragma: no cover - exercised via higher-level tests
        raise RuntimeError(
            "gliner2 is not installed in the worker environment"
        ) from exc
    return GLiNER2


def _registry_model_id(model_name: str) -> str | None:
    normalized = model_name.strip()
    if not normalized.startswith(_REGISTRY_MODEL_PREFIX):
        return None
    model_id = normalized[len(_REGISTRY_MODEL_PREFIX) :].strip()
    return model_id or None


def _registry_model_cache_root(model_id: str) -> Path:
    return Path(get_settings().WORK_DIR) / "model-cache" / model_id


def _safe_extract_archive(archive_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            member_path = (target_dir / member.name).resolve()
            try:
                member_path.relative_to(target_dir.resolve())
            except ValueError as exc:
                raise RuntimeError(
                    "Model artifact archive contains invalid paths"
                ) from exc
        archive.extractall(target_dir, filter="data")


def _resolve_adapter_dir(extracted_root: Path) -> Path:
    final_dir = extracted_root / "final"
    if final_dir.is_dir():
        return final_dir
    child_dirs = [path for path in extracted_root.iterdir() if path.is_dir()]
    if len(child_dirs) == 1:
        return child_dirs[0]
    return extracted_root


def _read_cached_registry_manifest(manifest_path: Path) -> str | None:
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    base_model = data.get("base_model") if isinstance(data, dict) else None
    if isinstance(base_model, str) and base_model.strip():
        return base_model.strip()
    return None


def _ensure_local_registry_model(
    model_id: str,
    *,
    task_id: str | None = None,
    task_secret: str | None = None,
) -> tuple[str, Path]:
    cache_root = _registry_model_cache_root(model_id)
    extracted_root = cache_root / "adapter"
    archive_path = cache_root / "artifact.tar.gz"
    manifest_path = cache_root / "manifest.json"
    has_cached_adapter = extracted_root.exists() and any(extracted_root.iterdir())
    adapter_dir = _resolve_adapter_dir(extracted_root) if has_cached_adapter else None
    cached_base_model = _read_cached_registry_manifest(manifest_path)

    if adapter_dir is not None and cached_base_model:
        return cached_base_model, adapter_dir

    if not task_id or not task_secret:
        raise RuntimeError("Task identity is required to download registry models")

    client = ApiClient()
    model = client.get_content_enrichment_registry_model(
        model_id,
        task_id=task_id,
        task_secret=task_secret,
    )
    if not extracted_root.exists() or not any(extracted_root.iterdir()):
        shutil.rmtree(extracted_root, ignore_errors=True)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        client.download_content_enrichment_model_artifact(
            model_id,
            archive_path,
            task_id=task_id,
            task_secret=task_secret,
        )
        _safe_extract_archive(archive_path, extracted_root)
    manifest_path.write_text(
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return model.base_model, _resolve_adapter_dir(extracted_root)


def _instantiate_extractor(
    model_name: str,
    *,
    task_id: str | None = None,
    task_secret: str | None = None,
):
    """Load and cache a GLiNER2 model instance."""
    GLiNER2 = _load_gliner2_class()
    registry_id = _registry_model_id(model_name)
    if registry_id is None:
        return GLiNER2.from_pretrained(model_name)

    base_model, adapter_dir = _ensure_local_registry_model(
        registry_id,
        task_id=task_id,
        task_secret=task_secret,
    )
    extractor = GLiNER2.from_pretrained(base_model)
    extractor.load_adapter(str(adapter_dir))
    return extractor


def _load_extractor(
    model_name: str,
    *,
    task_id: str | None = None,
    task_secret: str | None = None,
):
    """Load a GLiNER2 model, respecting worker model caching settings."""
    if not get_settings().KEEP_MODELS_LOADED:
        return _instantiate_extractor(
            model_name,
            task_id=task_id,
            task_secret=task_secret,
        )

    cached = _EXTRACTOR_CACHE.get(model_name)
    if cached is not None:
        return cached

    extractor = _instantiate_extractor(
        model_name,
        task_id=task_id,
        task_secret=task_secret,
    )
    if len(_EXTRACTOR_CACHE) >= _EXTRACTOR_CACHE_MAX_SIZE:
        oldest_key = next(iter(_EXTRACTOR_CACHE))
        _EXTRACTOR_CACHE.pop(oldest_key, None)
    _EXTRACTOR_CACHE[model_name] = extractor
    return extractor
