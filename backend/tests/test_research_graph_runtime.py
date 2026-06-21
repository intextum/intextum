"""Focused tests for research graph runtime helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from research.graph.runtime import (
    _load_single_context_document,
    _resolved_file_path,
    _semantic_search,
)


def test_resolved_file_path_uses_runtime_scope_mapping():
    """Resolved file paths should use the runtime context scope folder mapping."""
    runtime = SimpleNamespace(
        context_scope=SimpleNamespace(folder_uuid_to_name={"folder-docs": "documents"})
    )
    chunk = SimpleNamespace(
        resolved_file_path=lambda mapping: f"{mapping['folder-docs']}/report.pdf"
    )

    assert _resolved_file_path(runtime, chunk) == "documents/report.pdf"


@pytest.mark.asyncio
async def test_semantic_search_threads_scope_and_chunk_parsing():
    """Semantic search should embed once, query vectors once, and parse typed chunks."""
    runtime = SimpleNamespace(
        db="db-session",
        user=SimpleNamespace(username="alice"),
        settings=SimpleNamespace(EMBEDDING_MODEL="embed-model"),
        context_scope=SimpleNamespace(file_ids=["file-1", "file-2"]),
        embed_client=SimpleNamespace(
            embeddings=SimpleNamespace(
                create=AsyncMock(
                    return_value=SimpleNamespace(
                        data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
                    )
                )
            )
        ),
    )

    with (
        patch(
            "research.graph.runtime.VectorService.semantic_search",
            new=AsyncMock(return_value=["raw-result"]),
        ) as semantic_search,
        patch(
            "research.graph.runtime.parse_retrieved_chunks",
            return_value=["parsed-chunk"],
        ) as parse_chunks,
    ):
        result = await _semantic_search(runtime, "retrofit priorities", limit=4)

    assert result == ["parsed-chunk"]
    runtime.embed_client.embeddings.create.assert_awaited_once_with(
        model="embed-model",
        input=["retrofit priorities"],
    )
    semantic_search.assert_awaited_once_with(
        db="db-session",
        query_vector=[0.1, 0.2, 0.3],
        limit=4,
        file_ids=["file-1", "file-2"],
    )
    parse_chunks.assert_called_once_with(["raw-result"])


@pytest.mark.asyncio
async def test_load_single_context_document_fetches_full_text():
    """Single-file research should load a clipped full document."""
    runtime = SimpleNamespace(
        db="db-session",
        user=SimpleNamespace(username="alice"),
        settings=SimpleNamespace(CHAT_DOCUMENT_MAX_CHARS=80),
        context_scope=SimpleNamespace(
            constraints=[("documents/report.pdf", "folder-docs", "report.pdf")]
        ),
    )
    raw_chunks = [
        {
            "text": "Alpha section describes the selected document in detail.",
            "file_path": "report.pdf",
            "content_item_id": "content-1",
            "display_name": "report.pdf",
            "content_kind": "file",
            "page_numbers": [1],
            "doc_refs": ["#/texts/1"],
            "images": ["page-1.png"],
        },
        {
            "text": "Beta section continues with additional task-relevant details.",
            "file_path": "report.pdf",
            "content_item_id": "content-1",
            "display_name": "report.pdf",
            "content_kind": "file",
            "page_numbers": [2],
            "doc_refs": ["#/texts/2"],
            "images": ["page-2.png"],
        },
    ]

    with (
        patch(
            "research.graph.runtime.compute_content_item_id",
            return_value="content-1",
        ) as compute_id,
        patch(
            "research.graph.runtime.VectorService.fetch_document_chunks",
            new=AsyncMock(return_value=raw_chunks),
        ) as fetch_chunks,
    ):
        result = await _load_single_context_document(runtime)

    assert result is not None
    assert result["file_path"] == "documents/report.pdf"
    assert result["content_item_id"] == "content-1"
    assert result["display_name"] == "report.pdf"
    assert result["page_numbers"] == [1, 2]
    assert result["doc_refs"] == ["#/texts/1", "#/texts/2"]
    assert result["images"] == [
        "/api/content/extracted-asset/content-1/page-1.png",
        "/api/content/extracted-asset/content-1/page-2.png",
    ]
    assert result["text"].startswith("\n--- Page 1 ---\n\nAlpha section")
    assert "[... Truncated at 80 chars." in result["text"]
    compute_id.assert_called_once_with("folder-docs", "report.pdf")
    fetch_chunks.assert_awaited_once_with(
        db="db-session",
        content_item_id="content-1",
        limit=200,
    )
