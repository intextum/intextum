"""Vector database integration service (via backend proxy)."""

import hashlib
import logging
import uuid
from typing import Any

from docling_core.types.doc.document import PictureItem, TableItem

from models import WorkerVectorChunkPayload, WorkerVectorPoint
from services.api_client import ApiClient

logger = logging.getLogger(__name__)

NAMESPACE_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _build_image_uri_map(doc: Any) -> dict[str, str]:
    """Build a self_ref -> image URI lookup from a DoclingDocument."""
    uri_map = {}
    for item, _ in doc.iterate_items():
        if (
            isinstance(item, (PictureItem, TableItem))
            and hasattr(item, "image")
            and item.image
            and hasattr(item.image, "uri")
            and item.image.uri
        ):
            uri_map[item.self_ref] = str(item.image.uri)
    return uri_map


def _point_namespace(
    *,
    file_path: str,
    folder_uuid: str,
    metadata: dict[str, Any] | None,
) -> str:
    """Return the stable namespace used for point IDs for one file."""
    if isinstance(metadata, dict):
        content_item_id = metadata.get("content_item_id")
        if isinstance(content_item_id, str) and content_item_id:
            return content_item_id
    return f"{folder_uuid}:{file_path}"


def _build_chunk_payload(
    chunk: Any,
    file_path: str,
    index: int,
    image_uri_map: dict[str, str],
    *,
    index_version: str,
) -> WorkerVectorChunkPayload:
    """Build the payload for a single text chunk."""
    payload = WorkerVectorChunkPayload(
        file_path=file_path,
        text=chunk.text,
        chunk_index=index,
        index_version=index_version,
    )

    if not hasattr(chunk, "meta") or not chunk.meta:
        return payload

    meta = chunk.meta
    if hasattr(meta, "headings") and meta.headings:
        payload.headings = list(meta.headings)

    page_numbers: set[int] = set()
    images: list[str] = []
    doc_refs: list[str] = []

    if hasattr(meta, "doc_items") and meta.doc_items:
        for doc_item in meta.doc_items:
            if hasattr(doc_item, "self_ref") and doc_item.self_ref:
                doc_refs.append(doc_item.self_ref)
                if doc_item.self_ref in image_uri_map:
                    images.append(image_uri_map[doc_item.self_ref])
            if hasattr(doc_item, "prov") and doc_item.prov:
                for prov in doc_item.prov:
                    if hasattr(prov, "page_no") and prov.page_no is not None:
                        page_numbers.add(prov.page_no)

    if page_numbers:
        payload.page_numbers = sorted(page_numbers)
    if images:
        payload.images = images
    if doc_refs:
        payload.doc_refs = doc_refs

    return payload


def _build_vector_point(
    *,
    chunk: Any,
    vector: list[float],
    file_path: str,
    index: int,
    image_uri_map: dict[str, str],
    point_namespace_hash: str,
    index_version: str,
) -> WorkerVectorPoint:
    """Build one typed vector point for backend upsert."""
    point_id = str(uuid.uuid5(NAMESPACE_UUID, f"{point_namespace_hash}_{index}"))
    payload = _build_chunk_payload(
        chunk,
        file_path,
        index,
        image_uri_map,
        index_version=index_version,
    )
    return WorkerVectorPoint(id=point_id, vector=vector, payload=payload)


# pylint: disable=too-many-locals
def push_to_vector(
    file_path: str, chunks: list, *, task_id: str, task_secret: str, **kwargs
) -> None:
    """Embed and push text chunks to Postgres pgvector via backend proxy."""
    doc = kwargs.get("doc")
    metadata = kwargs.get("metadata")
    folder_uuid = kwargs.get("folder_uuid")

    client = ApiClient()
    logger.info("Generating embeddings for file %s", file_path)

    if folder_uuid is None:
        raise ValueError("folder_uuid is required for vector upsert")
    metadata_dict = metadata if isinstance(metadata, dict) else None
    content_item_id = (
        metadata_dict.get("content_item_id")
        if isinstance(metadata_dict, dict)
        else None
    )
    if not isinstance(content_item_id, str) or not content_item_id:
        content_item_id = None
    if not chunks:
        delete_from_vector(
            file_path,
            folder_uuid=folder_uuid,
            task_secret=task_secret,
            content_item_id=content_item_id,
        )
        return

    image_uri_map = _build_image_uri_map(doc) if doc else {}
    index_version = str(uuid.uuid4())
    point_namespace = _point_namespace(
        file_path=file_path,
        folder_uuid=folder_uuid,
        metadata=metadata_dict,
    )

    texts = [chunk.text for chunk in chunks]
    embeddings_list = client.get_embeddings(
        texts,
        task_id=task_id,
        task_secret=task_secret,
    )
    file_id_hash = hashlib.md5(point_namespace.encode()).hexdigest()

    points: list[WorkerVectorPoint] = []
    for i, (chunk, vector) in enumerate(zip(chunks, embeddings_list, strict=False)):
        point = _build_vector_point(
            chunk=chunk,
            vector=vector,
            file_path=file_path,
            index=i,
            image_uri_map=image_uri_map,
            point_namespace_hash=file_id_hash,
            index_version=index_version,
        )
        points.append(point)

    logger.info("Upserting %d text chunks for %s", len(points), file_path)
    client.upsert_points(
        points,
        folder_uuid=folder_uuid,
        task_id=task_id,
        task_secret=task_secret,
        metadata=metadata_dict,
    )

    # Cleanup stale points from older index versions after successful upsert.
    try:
        client.delete_points(
            file_path,
            folder_uuid=folder_uuid,
            task_secret=task_secret,
            content_item_id=content_item_id,
            exclude_version=index_version,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed stale-point cleanup for %s: %s", file_path, e)


def delete_from_vector(
    file_path: str,
    *,
    folder_uuid: str,
    task_secret: str,
    content_item_id: str | None = None,
    exclude_version: str | None = None,
) -> None:
    """Delete all points associated with a file path via backend proxy."""
    client = ApiClient()
    logger.info("Deleting points for file %s", file_path)
    client.delete_points(
        file_path,
        folder_uuid=folder_uuid,
        task_secret=task_secret,
        content_item_id=content_item_id,
        exclude_version=exclude_version,
    )
