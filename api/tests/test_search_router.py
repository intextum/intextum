"""Tests for search router helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.search import SearchResult
from routers.search import _best_file_results, _enrich_search_results, _execute_search
from routers.search import _derive_vector_path_filters, _normalize_path_prefix
from services.vector_dimensions import VectorDimensionMismatchError


def test_normalize_path_prefix_strips_slashes():
    """Path prefix normalization should trim leading/trailing slashes."""
    assert _normalize_path_prefix("/data/reports/") == "data/reports"


def test_derive_vector_path_filters_with_folder_and_relative_path():
    """API path with folder name should map to folder_uuid + relative prefix."""
    folder_uuid, relative_prefix = _derive_vector_path_filters(
        "data/reports",
        {"data": "folder-1"},
    )
    assert folder_uuid == "folder-1"
    assert relative_prefix == "reports"


def test_derive_vector_path_filters_with_folder_root_only():
    """Folder-only API path should map to folder_uuid and no relative prefix."""
    folder_uuid, relative_prefix = _derive_vector_path_filters(
        "data",
        {"data": "folder-1"},
    )
    assert folder_uuid == "folder-1"
    assert relative_prefix is None


def test_derive_vector_path_filters_without_folder_match():
    """Non-folder prefixes should be treated as relative_path filters."""
    folder_uuid, relative_prefix = _derive_vector_path_filters(
        "reports/2026",
        {"data": "folder-1"},
    )
    assert folder_uuid is None
    assert relative_prefix == "reports/2026"


def test_best_file_results_keeps_best_chunk_per_api_path():
    """Search response shaping should dedupe chunks by API path and keep order."""
    chunks = [
        SimpleNamespace(
            score=0.5,
            file_path="docs/a.pdf",
            folder_uuid="folder-1",
            content_item_id="file-a",
            display_name="A",
            content_kind="file",
            text="Lower score",
            chunk_index=0,
            page_numbers=[],
            headings=[],
            images=[],
            doc_refs=[],
        ),
        SimpleNamespace(
            score=0.9,
            file_path="docs/a.pdf",
            folder_uuid="folder-1",
            content_item_id="file-a",
            display_name="A",
            content_kind="file",
            text="Higher score",
            chunk_index=1,
            page_numbers=[],
            headings=[],
            images=[],
            doc_refs=[],
        ),
        SimpleNamespace(
            score=0.8,
            file_path="docs/b.pdf",
            folder_uuid="folder-1",
            content_item_id="file-b",
            display_name="B",
            content_kind="file",
            text="Other file",
            chunk_index=0,
            page_numbers=[],
            headings=[],
            images=[],
            doc_refs=[],
        ),
        SimpleNamespace(
            score=1.0,
            file_path="docs/hidden.pdf",
            folder_uuid="unknown-folder",
            content_item_id="hidden",
            display_name="Hidden",
            content_kind="file",
            text="No folder mapping",
            chunk_index=0,
            page_numbers=[],
            headings=[],
            images=[],
            doc_refs=[],
        ),
    ]

    results = _best_file_results(
        chunks,
        folder_name_map={"folder-1": "data"},
        path_prefix="data/docs",
    )

    assert [result.file_path for result in results] == [
        "data/docs/a.pdf",
        "data/docs/b.pdf",
    ]
    assert results[0].score == 0.9
    assert results[0].text == "Higher score"


@pytest.mark.asyncio
async def test_execute_search_passes_folder_and_relative_prefix_to_vector():
    """_execute_search should translate API prefix to DB folder/path filters."""
    settings = SimpleNamespace(
        EMBEDDING_MODEL="bge-m3",
    )
    embed_response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
    embed_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock(return_value=embed_response))
    )

    with (
        patch("routers.search.get_settings", return_value=settings),
        patch(
            "routers.search.ConnectorRuntimeService.connector_name_maps",
            return_value=({"data": "folder-1"}, {"folder-1": "data"}),
        ),
        patch("routers.search.get_async_embedding_client", return_value=embed_client),
        patch(
            "routers.search.VectorService.semantic_search",
            new=AsyncMock(return_value=[]),
        ) as semantic_search_mock,
    ):
        await _execute_search(
            db=AsyncMock(),
            q="test",
            limit=10,
            offset=0,
            content_kind="email_message",
            extension=None,
            path_prefix="data/reports",
            score_threshold=None,
        )

    await_args = semantic_search_mock.await_args
    assert await_args is not None
    assert await_args.kwargs["content_kind"] == "email_message"
    assert await_args.kwargs["folder_uuid"] == "folder-1"
    assert await_args.kwargs["path_prefix"] == "reports"


@pytest.mark.asyncio
async def test_execute_search_returns_502_when_embedding_backend_fails():
    settings = SimpleNamespace(EMBEDDING_MODEL="bge-m3")
    backend_error = RuntimeError("down")
    embed_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock(side_effect=backend_error))
    )

    with (
        patch("routers.search.get_settings", return_value=settings),
        patch(
            "routers.search.ConnectorRuntimeService.connector_name_maps",
            return_value=({}, {}),
        ),
        patch("routers.search.get_async_embedding_client", return_value=embed_client),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _execute_search(
                db=AsyncMock(),
                q="test",
                limit=10,
                offset=0,
                content_kind=None,
                extension=None,
                path_prefix=None,
                score_threshold=None,
            )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Embedding service unavailable"
    assert exc_info.value.__cause__ is backend_error


@pytest.mark.asyncio
async def test_execute_search_preserves_embedding_limit_errors():
    settings = SimpleNamespace(EMBEDDING_MODEL="bge-m3")
    limit_error = HTTPException(status_code=503, detail="Embedding service is busy")

    with (
        patch("routers.search.get_settings", return_value=settings),
        patch(
            "routers.search.ConnectorRuntimeService.connector_name_maps",
            return_value=({}, {}),
        ),
        patch("routers.search.get_async_embedding_client", return_value=object()),
        patch(
            "routers.search.create_embedding_response",
            new=AsyncMock(side_effect=limit_error),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _execute_search(
                db=AsyncMock(),
                q="test",
                limit=10,
                offset=0,
                content_kind=None,
                extension=None,
                path_prefix=None,
                score_threshold=None,
            )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Embedding service is busy"


@pytest.mark.asyncio
async def test_execute_search_returns_502_when_vector_backend_fails():
    settings = SimpleNamespace(EMBEDDING_MODEL="bge-m3")
    embed_response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
    embed_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock(return_value=embed_response))
    )
    backend_error = RuntimeError("down")

    with (
        patch("routers.search.get_settings", return_value=settings),
        patch(
            "routers.search.ConnectorRuntimeService.connector_name_maps",
            return_value=({}, {}),
        ),
        patch("routers.search.get_async_embedding_client", return_value=embed_client),
        patch(
            "routers.search.VectorService.semantic_search",
            new=AsyncMock(side_effect=backend_error),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _execute_search(
                db=AsyncMock(),
                q="test",
                limit=10,
                offset=0,
                content_kind=None,
                extension=None,
                path_prefix=None,
                score_threshold=None,
            )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Search backend unavailable"
    assert exc_info.value.__cause__ is backend_error


@pytest.mark.asyncio
async def test_execute_search_reports_vector_dimension_mismatch():
    settings = SimpleNamespace(EMBEDDING_MODEL="bge-m3")
    embed_response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
    embed_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock(return_value=embed_response))
    )

    with (
        patch("routers.search.get_settings", return_value=settings),
        patch(
            "routers.search.ConnectorRuntimeService.connector_name_maps",
            return_value=({}, {}),
        ),
        patch("routers.search.get_async_embedding_client", return_value=embed_client),
        patch(
            "routers.search.VectorService.semantic_search",
            new=AsyncMock(
                side_effect=VectorDimensionMismatchError(
                    "query_vector has 2 dimensions; expected 1024"
                )
            ),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _execute_search(
                db=AsyncMock(),
                q="test",
                limit=10,
                offset=0,
                content_kind=None,
                extension=None,
                path_prefix=None,
                score_threshold=None,
            )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Embedding vector dimension mismatch"


@pytest.mark.asyncio
async def test_enrich_search_results_adds_email_and_attachment_context():
    """Search-result enrichment should expose sender/date and attachment parent context."""
    email_record = SimpleNamespace(
        content_item_id="mail-1",
        display_name="Quarterly update",
        name="message.eml",
        content_kind="email_message",
        parent_content_item_id=None,
        email_message_details=SimpleNamespace(
            from_address="alice@example.com",
            sent_at="2026-04-27T10:15:00",
            received_at=None,
        ),
    )
    attachment_record = SimpleNamespace(
        content_item_id="att-1",
        display_name="report.pdf",
        name="report.pdf",
        content_kind="attachment",
        parent_content_item_id="mail-1",
        email_message_details=None,
    )
    parent_record = SimpleNamespace(
        content_item_id="mail-1",
        display_name="Quarterly update",
        name="message.eml",
    )

    db = AsyncMock()
    first_result = MagicMock()
    first_result.scalars.return_value.all.return_value = [
        email_record,
        attachment_record,
    ]
    second_result = MagicMock()
    second_result.scalars.return_value.all.return_value = [parent_record]
    db.execute.side_effect = [first_result, second_result]

    results = await _enrich_search_results(
        db,
        [
            SearchResult(
                score=0.91, file_path="mail/Inbox/message.eml", content_item_id="mail-1"
            ),
            SearchResult(
                score=0.84, file_path="mail/Inbox/report.pdf", content_item_id="att-1"
            ),
        ],
    )

    assert results[0].display_name == "Quarterly update"
    assert results[0].content_kind == "email_message"
    assert results[0].email_from_address == "alice@example.com"
    assert results[0].email_sent_at == "2026-04-27T10:15:00"
    assert results[1].content_kind == "attachment"
    assert results[1].parent_display_name == "Quarterly update"
