"""Document path and source helpers for chat tools."""

from chat.retrieval import RetrievedChunk
from chat.sources import CollectedSource


def resolve_document_path(
    file_path: str, folder_name_to_uuid: dict[str, str]
) -> tuple[str, str]:
    """Resolve an API path to (folder_uuid, relative_path)."""
    normalized_path = file_path.strip("/")
    if not normalized_path:
        raise ValueError("Document path is empty.")

    if "/" not in normalized_path:
        raise ValueError(
            "Document path must include folder name, e.g. 'projects/path/to/file.pdf'."
        )

    folder_name, relative_path = normalized_path.split("/", 1)
    if not relative_path:
        raise ValueError(
            "Document path must include a file path after the folder name."
        )

    folder_uuid = folder_name_to_uuid.get(folder_name)
    if not folder_uuid:
        raise ValueError(f"Data folder not found: {folder_name}")

    return folder_uuid, relative_path


def assemble_document_text(chunks: list[RetrievedChunk]) -> str:
    """Join sorted chunks into a single text with page boundaries."""
    parts = []
    last_page = None
    for chunk in chunks:
        text = chunk.text
        page_numbers = chunk.page_numbers

        if page_numbers:
            first_page = page_numbers[0]
            if first_page != last_page:
                parts.append(f"\n--- Page {first_page} ---\n")
                last_page = first_page
        parts.append(text)
    return "\n".join(parts)


def truncate_document_text(full_text: str, max_chars: int) -> str:
    """Limit document length to stay within model context constraints."""
    safe_max_chars = max(max_chars, 1)
    if len(full_text) <= safe_max_chars:
        return full_text
    return (
        full_text[:safe_max_chars]
        + f"\n\n[... Truncated at {safe_max_chars} chars. "
        + f"Total: {len(full_text)} chars.]"
    )


def build_document_source(
    file_path: str,
    chunks: list[RetrievedChunk],
    full_text: str,
    *,
    content_item_id: str | None,
    display_name: str | None,
) -> CollectedSource:
    """Build source metadata for source-document emission."""
    page_numbers: list[int] = []
    doc_refs: list[str] = []
    image_urls: list[str] = []
    seen_pages, seen_refs, seen_images = set(), set(), set()

    for chunk in chunks:
        for page in chunk.page_numbers:
            if page not in seen_pages:
                page_numbers.append(page)
                seen_pages.add(page)
        for doc_ref in chunk.doc_refs:
            if doc_ref not in seen_refs:
                doc_refs.append(doc_ref)
                seen_refs.add(doc_ref)
        for url in chunk.image_urls():
            if url not in seen_images:
                image_urls.append(url)
                seen_images.add(url)

    return CollectedSource(
        file_path=file_path,
        content_item_id=content_item_id,
        display_name=display_name,
        content_kind=chunks[0].content_kind if chunks else None,
        email_from_address=chunks[0].email_from_address if chunks else None,
        email_sent_at=chunks[0].email_sent_at if chunks else None,
        parent_display_name=chunks[0].parent_display_name if chunks else None,
        page_numbers=page_numbers,
        doc_refs=doc_refs,
        quote=full_text[:200],
        citation_index="document",
        image_urls=image_urls,
    )
