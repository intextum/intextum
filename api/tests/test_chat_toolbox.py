"""Tests for request-scoped chat tool orchestration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chat.runtime import ChatRuntime
from chat.toolbox import (
    ChatToolbox,
    DOCUMENT_OUTSIDE_CONTEXT_MESSAGE,
    NO_CONTEXT_FILES_MESSAGE,
)
from services.utils import compute_content_item_id


def _build_runtime(*, user, context_file_paths: list[str] | None = None) -> ChatRuntime:
    settings = SimpleNamespace(
        EMBEDDING_MODEL="test-embedding",
        CHAT_SEARCH_LIMIT=5,
        CHAT_DOCUMENT_MAX_CHARS=1000,
    )
    embed_create = AsyncMock()
    embed_client = SimpleNamespace(embeddings=SimpleNamespace(create=embed_create))
    return ChatRuntime(
        settings=settings,
        user=user,
        db=AsyncMock(),
        embed_client=embed_client,
        context_file_paths=context_file_paths or [],
    )


@pytest.mark.asyncio
async def test_search_documents_formats_results_and_collects_sources(
    runtime_sources, test_user, monkeypatch
):
    """Search tool should render numbered citations and record source metadata."""
    _ = runtime_sources
    runtime = _build_runtime(user=test_user)
    runtime.embed_client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2])]
    )
    semantic_search = AsyncMock(
        return_value=[
            {
                "text": "Quarterly results improved.",
                "file_path": "reports/quarterly.pdf",
                "folder_uuid": "folder-documents",
                "content_item_id": "file-1",
                "page_numbers": [1, 2],
                "doc_refs": ["ref-1"],
                "images": ["figures/page-1.png"],
            }
        ]
    )
    monkeypatch.setattr("chat.toolbox.VectorService.semantic_search", semantic_search)

    result = await ChatToolbox(runtime).search_documents("quarterly results")

    assert result == (
        "[1] Document: quarterly.pdf (p. 1, 2)\n"
        "Path: documents/reports/quarterly.pdf\n"
        "Quarterly results improved."
    )
    runtime.embed_client.embeddings.create.assert_awaited_once_with(
        model="test-embedding",
        input=["quarterly results"],
    )
    semantic_search.assert_awaited_once()
    assert len(runtime.source_collector.sources) == 1
    assert (
        runtime.source_collector.sources[0].file_path
        == "documents/reports/quarterly.pdf"
    )
    assert runtime.source_collector.sources[0].citation_index == 1
    assert runtime.source_collector.sources[0].doc_refs == ["ref-1"]
    assert runtime.source_collector.sources[0].image_urls == [
        "/api/content/extracted-asset/file-1/page-1.png"
    ]


@pytest.mark.asyncio
async def test_search_documents_short_circuits_when_selected_context_is_invalid(
    runtime_sources, test_user
):
    """Search tool should return the shared context error before embedding/searching."""
    _ = runtime_sources
    runtime = _build_runtime(user=test_user, context_file_paths=["missing/report.pdf"])

    result = await ChatToolbox(runtime).search_documents("anything")

    assert result == NO_CONTEXT_FILES_MESSAGE
    runtime.embed_client.embeddings.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_document_builds_full_text_and_records_document_source(
    runtime_sources, test_user, monkeypatch
):
    """Document tool should assemble full text and keep citation asset metadata."""
    _ = runtime_sources
    runtime = _build_runtime(user=test_user)
    fetch_document_chunks = AsyncMock(
        return_value=[
            {
                "text": "First section",
                "page_numbers": [1],
                "doc_refs": ["ref-1"],
                "content_item_id": "file-1",
                "images": ["figures/page-1.png"],
            },
            {
                "text": "Second section",
                "page_numbers": [2],
                "doc_refs": ["ref-2"],
                "content_item_id": "file-1",
                "images": ["page-2.png"],
            },
        ]
    )
    monkeypatch.setattr(
        "chat.toolbox.VectorService.fetch_document_chunks",
        fetch_document_chunks,
    )

    result = await ChatToolbox(runtime).get_document("documents/report.pdf")

    assert result == (
        "# Full document: report.pdf\n\n"
        "\n--- Page 1 ---\n\n"
        "First section\n"
        "\n--- Page 2 ---\n\n"
        "Second section"
    )
    fetch_document_chunks.assert_awaited_once_with(
        db=runtime.db,
        content_item_id=compute_content_item_id("folder-documents", "report.pdf"),
        limit=200,
    )
    assert len(runtime.source_collector.sources) == 1
    assert runtime.source_collector.sources[0].file_path == "documents/report.pdf"
    assert runtime.source_collector.sources[0].citation_index == "document"
    assert runtime.source_collector.sources[0].doc_refs == ["ref-1", "ref-2"]
    assert runtime.source_collector.sources[0].image_urls == [
        "/api/content/extracted-asset/file-1/page-1.png",
        "/api/content/extracted-asset/file-1/page-2.png",
    ]


@pytest.mark.asyncio
async def test_get_document_respects_selected_context_scope(
    runtime_sources, test_user, monkeypatch
):
    """Document tool should block reads outside the selected context set."""
    _ = runtime_sources
    runtime = _build_runtime(user=test_user, context_file_paths=["documents/file1.pdf"])
    fetch_document_chunks = AsyncMock()
    monkeypatch.setattr(
        "chat.toolbox.VectorService.fetch_document_chunks",
        fetch_document_chunks,
    )

    result = await ChatToolbox(runtime).get_document("documents/other.pdf")

    assert result == DOCUMENT_OUTSIDE_CONTEXT_MESSAGE
    fetch_document_chunks.assert_not_awaited()
