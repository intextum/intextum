"""Tests for vector service ACL filtering behavior."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.vector import VectorChunkUpsert, VectorDocumentChunk
from services.vector import VectorService
from services.vector_dimensions import VectorDimensionMismatchError


def _mock_db_with_empty_result() -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute.return_value = result
    return db


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        ACL_ENABLED=True,
        EMBEDDING_VECTOR_SIZE=1024,
        MAX_VECTOR_CHUNK_LIMIT=1000,
    )


def _vector() -> list[float]:
    return [0.1] * 1024


def test_document_chunk_to_result_keeps_file_assets_for_chat_document_sources():
    """Document-chunk projection should expose file/image data for chat citations."""
    chunk = SimpleNamespace(
        text="Example",
        chunk_index=3,
        page_numbers=[1],
        headings=["Section"],
        images=["figures/page-1.png"],
        doc_refs=["ref-1"],
    )
    file = SimpleNamespace(
        relative_path="docs/report.pdf",
        content_item_id="file-1",
        display_name="Quarterly Report",
        content_kind="email_message",
        name="report.pdf",
    )

    result = VectorService._document_chunk_to_result(
        chunk,
        file,
        source_metadata={
            "email_from_address": "alice@example.com",
            "email_sent_at": datetime(2026, 4, 27, 10, 0, 0),
            "parent_display_name": "Quarterly update",
        },
    )

    assert result == VectorDocumentChunk(
        file_path="docs/report.pdf",
        content_item_id="file-1",
        display_name="Quarterly Report",
        content_kind="email_message",
        email_from_address="alice@example.com",
        email_sent_at=datetime(2026, 4, 27, 10, 0, 0),
        parent_display_name="Quarterly update",
        text="Example",
        chunk_index=3,
        page_numbers=[1],
        headings=["Section"],
        images=["figures/page-1.png"],
        doc_refs=["ref-1"],
    )


def test_search_row_to_result_keeps_display_name_and_content_kind():
    """Semantic search rows should retain the content item display metadata."""
    chunk = SimpleNamespace(
        text="Example",
        chunk_index=1,
        page_numbers=[],
        headings=[],
        images=[],
        doc_refs=[],
    )
    file = SimpleNamespace(
        relative_path="Inbox/message.eml",
        folder_uuid="mail",
        content_item_id="mail-1",
        display_name="Quarterly update",
        content_kind="email_message",
        name="message.eml",
    )

    result = VectorService._search_row_to_result(
        chunk,
        file,
        0.91,
        source_metadata={
            "email_from_address": "alice@example.com",
            "email_sent_at": datetime(2026, 4, 27, 10, 0, 0),
            "parent_display_name": "Inbox thread",
        },
    )

    assert result.score == 0.91
    assert result.content_item_id == "mail-1"
    assert result.display_name == "Quarterly update"
    assert result.content_kind == "email_message"
    assert result.email_from_address == "alice@example.com"
    assert result.parent_display_name == "Inbox thread"


@pytest.mark.asyncio
async def test_semantic_search_relies_on_database_rls_for_visibility():
    """Vector search should leave ACL enforcement to Postgres RLS."""
    db = _mock_db_with_empty_result()

    with patch("services.vector.get_settings", return_value=_settings()):
        await VectorService.semantic_search(
            db=db,
            query_vector=_vector(),
            limit=5,
        )

    stmt = db.execute.call_args.args[0]
    where_sql = str(stmt.whereclause)
    assert "allowed_viewers" not in where_sql
    assert "denied_viewers" not in where_sql


@pytest.mark.asyncio
async def test_semantic_search_applies_content_kind_filter():
    """Semantic search should constrain by content kind when requested."""
    db = _mock_db_with_empty_result()

    with patch("services.vector.get_settings", return_value=_settings()):
        await VectorService.semantic_search(
            db=db,
            query_vector=_vector(),
            limit=5,
            content_kind="email_message",
        )

    stmt = db.execute.call_args.args[0]
    where_sql = str(stmt.whereclause)
    assert "content_kind" in where_sql
    assert stmt.compile().params["content_kind_1"] == "email_message"


@pytest.mark.asyncio
async def test_fetch_document_chunks_relies_on_database_rls_for_visibility():
    """Document chunk reads should leave ACL enforcement to Postgres RLS."""
    db = _mock_db_with_empty_result()

    with patch("services.vector.get_settings", return_value=_settings()):
        await VectorService.fetch_document_chunks(
            db=db,
            content_item_id="file-1",
            limit=10,
        )

    stmt = db.execute.call_args.args[0]
    where_sql = str(stmt.whereclause)
    assert "allowed_viewers" not in where_sql
    assert "denied_viewers" not in where_sql


@pytest.mark.asyncio
async def test_semantic_search_does_not_generate_app_acl_clause():
    """The denied_viewers SQL clause is replaced by database RLS."""
    db = _mock_db_with_empty_result()

    with patch("services.vector.get_settings", return_value=_settings()):
        await VectorService.semantic_search(
            db=db,
            query_vector=_vector(),
            limit=5,
        )

    stmt = db.execute.call_args.args[0]
    where_sql = str(stmt.whereclause)
    assert "denied_viewers IS NULL" not in where_sql


@pytest.mark.asyncio
async def test_semantic_search_rejects_wrong_query_vector_dimension_before_db():
    db = _mock_db_with_empty_result()

    with patch("services.vector.get_settings", return_value=_settings()):
        with pytest.raises(VectorDimensionMismatchError) as exc_info:
            await VectorService.semantic_search(
                db=db,
                query_vector=[0.1, 0.2],
                limit=5,
            )

    assert str(exc_info.value) == "query_vector has 2 dimensions; expected 1024"
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_chunks_rejects_wrong_vector_dimension_before_db():
    db = _mock_db_with_empty_result()
    chunks = [
        VectorChunkUpsert(
            id="chunk-1",
            text="Example",
            embedding=[0.1, 0.2],
            chunk_index=0,
            index_version="v1",
        )
    ]

    with patch("services.vector.get_settings", return_value=_settings()):
        with pytest.raises(VectorDimensionMismatchError) as exc_info:
            await VectorService.upsert_chunks(db, "file-1", chunks)

    assert str(exc_info.value) == ("chunk.embedding[0] has 2 dimensions; expected 1024")
    db.execute.assert_not_awaited()
