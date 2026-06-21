"""Kind-aware behavior policy for content items."""

from __future__ import annotations

from models.content.items import ContentItemCapabilities, ContentItemKind
from services.content.invariants import safe_content_item_kind


def content_item_capabilities(
    kind: ContentItemKind | str | None,
) -> ContentItemCapabilities:
    """Return the behavior capabilities for one content kind."""
    resolved = safe_content_item_kind(kind)

    if resolved == ContentItemKind.FOLDER:
        return ContentItemCapabilities(
            supports_chunking=False,
            supports_search=False,
            supports_enrichment=False,
            supports_review=False,
        )

    if resolved == ContentItemKind.EMAIL_MESSAGE:
        return ContentItemCapabilities(
            supports_chunking=True,
            supports_search=True,
            supports_enrichment=True,
            supports_review=True,
        )

    if resolved == ContentItemKind.ATTACHMENT:
        return ContentItemCapabilities(
            supports_chunking=True,
            supports_search=True,
            supports_enrichment=True,
            supports_review=True,
        )

    return ContentItemCapabilities(
        supports_chunking=True,
        supports_search=True,
        supports_enrichment=True,
        supports_review=True,
    )
