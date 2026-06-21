"""Shared URL, payload, and response helpers for the worker backend client."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from pydantic import BaseModel


def build_worker_url(base_url: str, path: str) -> str:
    """Build one backend worker URL from a normalized base URL and path."""
    return f"{base_url.rstrip('/')}{path}"


def encode_relative_path(relative_path: str) -> str:
    """Encode one relative file path for worker backend URLs."""
    return quote(relative_path, safe="/")


def resolve_download_target(
    local_dir: Path,
    relative_path: str,
    *,
    download_key: str | None = None,
) -> Path:
    """Resolve the local download target path for one backend file."""
    target_dir = local_dir
    if isinstance(download_key, str) and download_key.strip():
        target_dir = local_dir / download_key.strip()
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / Path(relative_path).name


def write_download_stream(
    resp: requests.Response,
    local_path: Path,
    *,
    chunk_size: int = 1024 * 1024,
) -> None:
    """Persist a streamed backend download to disk."""
    with open(local_path, "wb") as handle:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            handle.write(chunk)


def raise_for_status_with_detail(resp: requests.Response) -> None:
    """Raise HTTPError and attach backend detail when available."""
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        detail = None
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                raw_detail = payload.get("detail")
                if raw_detail is not None:
                    detail = str(raw_detail)
            elif payload is not None:
                detail = str(payload)
        except ValueError:
            body = resp.text.strip()
            if body:
                detail = body[:500]

        if detail:
            raise requests.exceptions.HTTPError(
                f"{exc}. Backend detail: {detail}",
                request=resp.request,
                response=resp,
            ) from exc
        raise


def model_payload(model: Any, *, exclude_none: bool = False) -> dict[str, Any]:
    """Serialize one pydantic request model into a request-ready payload."""
    return model.model_dump(exclude_none=exclude_none)


def typed_json_response[ModelT: BaseModel](
    resp: requests.Response, model_cls: type[ModelT]
) -> ModelT:
    """Validate one JSON response against the requested response model."""
    raise_for_status_with_detail(resp)
    return model_cls.model_validate(resp.json())


def typed_optional_json_response[ModelT: BaseModel](
    resp: requests.Response,
    model_cls: type[ModelT],
    *,
    none_status: int,
) -> ModelT | None:
    """Return None for one expected empty status, else validate typed JSON."""
    if resp.status_code == none_status:
        return None
    return typed_json_response(resp, model_cls)
