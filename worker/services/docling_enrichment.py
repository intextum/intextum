"""Picture enrichment extraction and synthetic picture injection helpers."""

from typing import Any

_PREDICTION_LIST_KEYS = ("predictions", "predicted_classes", "classes")
_PREDICTION_LABEL_KEYS = ("class_name", "label", "name", "class", "category")
_PREDICTION_SCORE_KEYS = ("confidence", "score", "probability")


def _prediction_list_from_classification(value: Any) -> list[dict]:
    """Return normalized prediction dictionaries from known Docling shapes."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]

    if not isinstance(value, dict):
        return []

    for key in _PREDICTION_LIST_KEYS:
        predictions = value.get(key)
        if isinstance(predictions, list):
            return [item for item in predictions if isinstance(item, dict)]

    if any(key in value for key in _PREDICTION_LABEL_KEYS):
        return [value]

    return []


def _picture_predictions(picture: dict) -> list[dict]:
    meta = picture.get("meta")
    if isinstance(meta, dict):
        predictions = _prediction_list_from_classification(meta.get("classification"))
        if predictions:
            return predictions

    predictions = _prediction_list_from_classification(picture.get("classification"))
    if predictions:
        return predictions

    return []


def _prediction_score(prediction: dict) -> float:
    for key in _PREDICTION_SCORE_KEYS:
        value = prediction.get(key)
        if isinstance(value, int | float):
            return float(value)
    return 0.0


def _prediction_label(prediction: dict) -> str:
    for key in _PREDICTION_LABEL_KEYS:
        value = prediction.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _description_text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    if not isinstance(value, dict):
        return None

    for key in ("text", "description", "caption"):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()

    return None


def _picture_description(picture: dict) -> str | None:
    meta = picture.get("meta")
    if isinstance(meta, dict):
        description = _description_text(meta.get("description"))
        if description is not None:
            return description

    description = _description_text(picture.get("description"))
    if description is not None:
        return description

    return None


def _picture_image_uri(picture: dict) -> str | None:
    image = picture.get("image")
    if isinstance(image, dict):
        uri = image.get("uri")
        if isinstance(uri, str) and uri:
            return uri
    elif isinstance(image, str) and image:
        return image

    uri = picture.get("image_uri")
    return uri if isinstance(uri, str) and uri else None


def extract_picture_enrichments(document_dict: dict) -> dict:
    """Extract picture classification and description from document dict."""
    enrichments = {}

    for picture in document_dict.get("pictures", []):
        if not isinstance(picture, dict):
            continue

        uri = _picture_image_uri(picture)
        if not uri:
            continue

        label = "unknown"
        score = 0.0
        predictions = _picture_predictions(picture)
        if predictions:
            best = max(predictions, key=_prediction_score)
            label = _prediction_label(best)
            score = _prediction_score(best)

        enrichments[uri] = {
            "label": label,
            "score": score,
            "description": _picture_description(picture),
        }

    return enrichments


def increment_picture_refs(obj):
    """Increment all #/pictures/N references by 1."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if (
                key in ("self_ref", "$ref")
                and isinstance(value, str)
                and value.startswith("#/pictures/")
            ):
                idx = int(value.rsplit("/", 1)[1])
                obj[key] = f"#/pictures/{idx + 1}"
            else:
                increment_picture_refs(value)
    elif isinstance(obj, list):
        for item in obj:
            increment_picture_refs(item)


def inject_standalone_image_as_picture(
    document_dict: dict,
    page_image_uri: str,
    description: str | None,
    page_image: dict | None = None,
    page: dict | None = None,
) -> None:
    """Insert a synthetic picture entry for a standalone image into the document dict."""
    image_data: dict = {"uri": page_image_uri}
    if page_image:
        for key in ("mimetype", "dpi", "size"):
            if key in page_image:
                image_data[key] = page_image[key]

    picture: dict = {
        "self_ref": "#/pictures/0",
        "parent": {"$ref": "#/body"},
        "children": [],
        "content_layer": "body",
        "label": "picture",
        "image": image_data,
        "captions": [],
        "references": [],
        "footnotes": [],
        "meta": {
            "classification": {
                "predictions": [{"class_name": "natural_image", "confidence": 1.0}]
            }
        },
    }

    if page:
        page_size = page.get("size", {})
        picture["prov"] = [
            {
                "page_no": page.get("page_no", 1),
                "bbox": {
                    "l": 0.0,
                    "t": 0.0,
                    "r": page_size.get("width", 0.0),
                    "b": page_size.get("height", 0.0),
                    "coord_origin": "TOPLEFT",
                },
                "charspan": [0, 0],
            }
        ]

    if description:
        picture["meta"]["description"] = {"text": description}

    increment_picture_refs(document_dict)
    document_dict.setdefault("pictures", []).insert(0, picture)

    body = document_dict.get("body")
    if body is not None:
        body.setdefault("children", []).insert(0, {"$ref": "#/pictures/0"})
