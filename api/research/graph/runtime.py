"""Runtime and retrieval helpers for the research graph."""

from __future__ import annotations

from typing import Any

from chat.documents import assemble_document_text, truncate_document_text
from chat.retrieval import parse_retrieved_chunks
from services.ai_limits import create_embedding_response
from services.content.enrichment_context import load_effective_context_file_enrichment
from services.utils import compute_content_item_id
from services.vector import VectorService

DOCUMENT_FETCH_LIMIT = 200


def _resolved_file_path(runtime, chunk) -> str:
    return chunk.resolved_file_path(runtime.context_scope.folder_uuid_to_name)


async def _semantic_search(runtime, query: str, *, limit: int) -> list[Any]:
    response = await create_embedding_response(
        runtime.embed_client,
        runtime.settings,
        model=runtime.settings.EMBEDDING_MODEL,
        texts=[query],
    )
    query_vector = response.data[0].embedding
    results = await VectorService.semantic_search(
        db=runtime.db,
        query_vector=query_vector,
        limit=limit,
        file_ids=runtime.context_scope.file_ids or None,
    )
    return parse_retrieved_chunks(results)


async def _load_single_context_document(runtime) -> dict[str, Any] | None:
    """Load the full selected document when research is scoped to one file."""
    constraints = list(getattr(runtime.context_scope, "constraints", []) or [])
    if len(constraints) != 1:
        return None

    api_path, folder_uuid, relative_path = constraints[0]
    content_item_id = compute_content_item_id(folder_uuid, relative_path)
    results = await VectorService.fetch_document_chunks(
        db=runtime.db,
        content_item_id=content_item_id,
        limit=DOCUMENT_FETCH_LIMIT,
    )
    chunks = parse_retrieved_chunks(results)
    if not chunks:
        return None

    full_text = truncate_document_text(
        assemble_document_text(chunks),
        getattr(runtime.settings, "CHAT_DOCUMENT_MAX_CHARS", 30000),
    )
    if not full_text.strip():
        return None

    page_numbers: list[int] = []
    doc_refs: list[str] = []
    image_urls: list[str] = []
    seen_pages: set[int] = set()
    seen_refs: set[str] = set()
    seen_images: set[str] = set()
    for chunk in chunks:
        for page in chunk.page_numbers:
            if page not in seen_pages:
                page_numbers.append(page)
                seen_pages.add(page)
        for doc_ref in chunk.doc_refs:
            if doc_ref not in seen_refs:
                doc_refs.append(doc_ref)
                seen_refs.add(doc_ref)
        for image_url in chunk.image_urls():
            if image_url not in seen_images:
                image_urls.append(image_url)
                seen_images.add(image_url)

    first_chunk = chunks[0]
    return {
        "file_path": api_path,
        "content_item_id": content_item_id,
        "display_name": first_chunk.display_name,
        "content_kind": first_chunk.content_kind.value,
        "email_from_address": first_chunk.email_from_address,
        "email_sent_at": (
            first_chunk.email_sent_at.isoformat()
            if first_chunk.email_sent_at is not None
            else None
        ),
        "parent_display_name": first_chunk.parent_display_name,
        "page_numbers": page_numbers,
        "doc_refs": doc_refs,
        "images": image_urls,
        "text": full_text,
    }


async def _collect_structured_facts(
    runtime,
    state,
    *,
    loader=load_effective_context_file_enrichment,
) -> dict[str, Any]:
    del state
    return {
        "structured_facts": await loader(
            db=runtime.db,
            user=runtime.user,
            context_scope=runtime.context_scope,
        )
    }
