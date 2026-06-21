"""Helpers for inspecting and rewriting Docling document.json output."""

from __future__ import annotations

from typing import Set

_TABLE_CLASSES: Set[str] = {"table", "document_index"}
_PICTURE_CLASSIFICATION_KEYS = ("predictions", "predicted_classes", "classes")
_PICTURE_LABEL_KEYS = ("class_name", "label", "name", "class", "category")
_PICTURE_SCORE_KEYS = ("confidence", "score", "probability")


def classify_images_from_docling(doc: dict) -> dict[str, str]:
    """Classify extracted image filenames from document.json."""
    return {
        filename: str(meta["type"])
        for filename, meta in extract_image_metadata_from_docling(doc).items()
        if meta.get("type") is not None
    }


def extract_image_metadata_from_docling(
    doc: dict,
) -> dict[str, dict[str, str | None]]:
    """Extract per-filename metadata (type, classification, description) from doc.json."""
    if not doc:
        return {}

    metadata: dict[str, dict[str, str | None]] = {}

    for page in doc.get("pages", {}).values():
        uri = (page.get("image") or {}).get("uri", "")
        if uri:
            metadata[_filename_from_uri(uri)] = {
                "type": "page",
                "classification": None,
                "description": None,
            }

    for table in doc.get("tables", []):
        uri = (table.get("image") or {}).get("uri", "")
        if not uri:
            continue
        description = _description_from_picture(table)
        metadata[_filename_from_uri(uri)] = {
            "type": "table",
            "classification": None,
            "description": description,
        }

    for picture in doc.get("pictures", []):
        uri = (picture.get("image") or {}).get("uri", "")
        if not uri:
            continue
        filename = _filename_from_uri(uri)
        asset_type = "table" if _is_table_picture(picture) else "figure"
        metadata[filename] = {
            "type": asset_type,
            "classification": _classification_label_from_picture(picture),
            "description": _description_from_picture(picture),
        }

    return metadata


def rewrite_uris(obj, prefix: str, dir_name: str):
    """Recursively rewrite URI paths in document JSON to API-accessible URLs."""

    def _rewrite_uri(value: str) -> str:
        if value.startswith("/"):
            marker = f"/{dir_name}/"
            idx = value.find(marker)
            if idx != -1:
                return prefix + value[idx + len(marker) :]
            return prefix + value.rsplit("/", 1)[-1]
        return prefix + value

    if isinstance(obj, dict):
        for key, value in obj.items():
            if (
                key == "uri"
                and isinstance(value, str)
                and not value.startswith(("http://", "https://", "data:"))
            ):
                obj[key] = _rewrite_uri(value)
            else:
                rewrite_uris(value, prefix, dir_name)
    elif isinstance(obj, list):
        for item in obj:
            rewrite_uris(item, prefix, dir_name)


def _filename_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _description_from_picture(picture: dict) -> str | None:
    meta = picture.get("meta")
    if isinstance(meta, dict):
        for key in ("description", "caption"):
            description = description_text_from_meta_value(meta.get(key))
            if description is not None:
                return description

    return None


def description_text_from_meta_value(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None

    for key in ("text", "description", "caption"):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _classification_label_from_picture(picture: dict) -> str | None:
    predictions = _picture_predictions(picture)
    if not predictions:
        return None
    best = max(predictions, key=_prediction_score)
    return _prediction_label(best)


def prediction_list_from_classification(value: object) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]

    if not isinstance(value, dict):
        return []

    for key in _PICTURE_CLASSIFICATION_KEYS:
        predictions = value.get(key)
        if isinstance(predictions, list):
            return [item for item in predictions if isinstance(item, dict)]

    if any(key in value for key in _PICTURE_LABEL_KEYS):
        return [value]

    return []


def _picture_predictions(picture: dict) -> list[dict]:
    meta = picture.get("meta")
    if isinstance(meta, dict):
        predictions = prediction_list_from_classification(meta.get("classification"))
        if predictions:
            return predictions

    predictions = prediction_list_from_classification(picture.get("classification"))
    if predictions:
        return predictions

    return []


def _prediction_label(prediction: dict) -> str | None:
    for key in _PICTURE_LABEL_KEYS:
        value = prediction.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _prediction_score(prediction: dict) -> float:
    for key in _PICTURE_SCORE_KEYS:
        value = prediction.get(key)
        if isinstance(value, int | float):
            return float(value)
    return 0.0


def _is_table_picture(picture: dict) -> bool:
    predictions = _picture_predictions(picture)
    if not predictions:
        return False

    best_prediction = max(predictions, key=_prediction_score)
    return _prediction_label(best_prediction) in _TABLE_CLASSES
