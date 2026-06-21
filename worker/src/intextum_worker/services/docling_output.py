"""Output serialization helpers for Docling conversion results."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from docling_core.types.doc.base import ImageRefMode


def save_conversion_results(
    conv_result, output_dir: Path, **_kwargs
) -> tuple[dict, list[str]]:
    """Save conversion results with all images referenced relatively."""
    # pylint: disable=unused-argument
    conv_result.document.save_as_json(
        output_dir / "document.json",
        artifacts_dir=output_dir,
        image_mode=ImageRefMode.REFERENCED,
    )

    with open(output_dir / "document.json", encoding="utf-8") as f:
        document_dict = json.load(f)

    output_dir_str = str(output_dir.resolve()) + "/"
    relativize_uris(document_dict, output_dir_str)
    save_inline_images(document_dict, output_dir)

    with open(output_dir / "document.json", "w", encoding="utf-8") as f:
        json.dump(document_dict, f)

    doc_images = [
        str(img_file.relative_to(output_dir)) for img_file in output_dir.rglob("*.png")
    ]
    return document_dict, doc_images


def relativize_uris(obj, prefix: str):
    """Recursively replace absolute URI paths starting with prefix to relative."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "uri" and isinstance(value, str) and value.startswith(prefix):
                obj[key] = value[len(prefix) :]
            else:
                relativize_uris(value, prefix)
    elif isinstance(obj, list):
        for item in obj:
            relativize_uris(item, prefix)


def save_inline_images(document_dict: dict, output_dir: Path):
    """Extract base64 table/page image data URIs and persist them as files."""

    def _save_data_uri(image_obj: dict, prefix: str, index: int) -> None:
        uri = image_obj.get("uri", "")
        if not uri.startswith("data:"):
            return
        try:
            header, b64data = uri.split(",", 1)
            ext = "jpg" if "image/jpeg" in header else "png"
            img_bytes = base64.b64decode(b64data)
            img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
            filename = f"{prefix}_{index:06d}_{img_hash}.{ext}"
            (output_dir / filename).write_bytes(img_bytes)
            image_obj["uri"] = filename
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    for i, table in enumerate(document_dict.get("tables", [])):
        image = table.get("image")
        if image:
            _save_data_uri(image, "table", i)

    pages = document_dict.get("pages", {})
    for page_no, page in pages.items():
        image = page.get("image")
        if image:
            _save_data_uri(image, "page", int(page_no))
