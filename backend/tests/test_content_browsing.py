"""Tests for content browsing route helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routers.content.browsing import get_content_chunks


@pytest.mark.asyncio
async def test_get_content_chunks_logs_vector_failures_with_cause(caplog):
    backend_error = RuntimeError("vector unavailable")

    with (
        patch(
            "routers.content.browsing.resolve_authorized_source_file",
            new=AsyncMock(
                return_value=(SimpleNamespace(uuid="folder-1"), "docs/file.pdf")
            ),
        ),
        patch(
            "routers.content.browsing.VectorService.fetch_document_chunks",
            new=AsyncMock(side_effect=backend_error),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_content_chunks(
                "documents/docs/file.pdf",
                limit=100,
                offset=0,
                user=SimpleNamespace(),
                file_service=SimpleNamespace(),
                db=AsyncMock(),
            )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Failed to fetch file chunks"
    assert exc_info.value.__cause__ is backend_error
    assert "Vector DB error for documents/docs/file.pdf" in caplog.text
