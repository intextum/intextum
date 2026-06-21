"""Docling-specific helpers shared by worker processors."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from intextum_worker.processor_runtime import LoggerType


def save_document_json(output_dir: Path, document_dict: dict) -> None:
    """Persist the current Docling document JSON to disk."""
    with open(output_dir / "document.json", "w", encoding="utf-8") as handle:
        json.dump(document_dict, handle)


def find_first_page_image(
    document_dict: dict,
) -> tuple[str | None, dict | None, dict | None]:
    """Return the first page-level image entry from a Docling document."""
    pages = document_dict.get("pages", {})
    if not isinstance(pages, dict):
        return None, None, None

    for page in pages.values():
        if not isinstance(page, dict):
            continue
        image = page.get("image", {})
        if isinstance(image, dict) and image.get("uri"):
            return str(image["uri"]), image, page
    return None, None, None


def maybe_describe_standalone_image(
    document_dict: dict,
    *,
    file_path: Path,
    output_dir: Path,
    task_id: str,
    task_secret: str,
    content_item_id: str,
    log: LoggerType,
    describe_image: Callable[..., str | None],
    inject_picture: Callable[..., None],
    persist_document_json: Callable[[Path, dict], None] = save_document_json,
) -> None:
    """Describe a standalone image file via VLM and inject it as a picture."""
    log.info("Image file detected, describing full image via VLM")
    page_image_uri, page_image, page_dict = find_first_page_image(document_dict)

    description = None
    if page_image_uri:
        try:
            image_for_vlm = (
                output_dir / page_image_uri
                if not Path(page_image_uri).is_absolute()
                else Path(page_image_uri)
            )
            description = describe_image(
                image_for_vlm,
                task_id=task_id,
                task_secret=task_secret,
                content_item_id=content_item_id,
            )
            log.info("VLM description obtained for full image")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning(
                "Failed to get VLM description for image",
                extra={"error": str(exc)},
            )

    inject_picture(
        document_dict,
        page_image_uri or file_path.name,
        description,
        page_image=page_image,
        page=page_dict,
    )
    persist_document_json(output_dir, document_dict)


def chunk_docling_document(
    document_dict: dict,
    *,
    api_client_factory: Callable[[], Any],
    tokenizer_cls: Callable[..., Any],
    task_id: str,
    task_secret: str,
) -> tuple[object, list, str]:
    """Build Docling chunks via the configured backend tokenizer."""
    # pylint: disable=import-outside-toplevel
    from docling.chunking import HybridChunker
    from docling.datamodel.document import DoclingDocument

    doc = DoclingDocument.model_validate(document_dict)
    client = api_client_factory()
    config = client.get_config()
    max_tokens = config.embedding_max_tokens
    if max_tokens <= 0:
        raise ValueError("embedding_max_tokens must be a positive integer.")

    embedding_model_name = config.embedding_model
    tokenizer = tokenizer_cls(
        client=client,
        max_tokens=max_tokens,
        task_id=task_id,
        task_secret=task_secret,
    )
    chunker = HybridChunker(tokenizer=tokenizer)
    chunks = list(chunker.chunk(doc))
    return doc, chunks, embedding_model_name
