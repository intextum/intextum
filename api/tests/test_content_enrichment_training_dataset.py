"""Unit tests for training-dataset input contextualization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.content_enrichment_training.dataset import (
    ChunkRecord,
    ContentEnrichmentTrainingDatasetBuilder,
    _contextualize_chunk,
    document_text_from_chunk_records,
    normalize_training_input,
)


def test_contextualize_chunk_prepends_heading_path_before_body():
    record = ChunkRecord(
        text="Body text with details.",
        headings=["Section A", "Subsection 1"],
    )

    rendered = _contextualize_chunk(record)

    assert rendered == "Section A\nSubsection 1\n\nBody text with details."


def test_contextualize_chunk_returns_body_only_when_no_headings():
    record = ChunkRecord(text="Just the body.", headings=[])

    assert _contextualize_chunk(record) == "Just the body."


def test_contextualize_chunk_ignores_blank_or_non_string_headings():
    record = ChunkRecord(
        text="Body",
        headings=["", "  ", "Real heading"],
    )

    assert _contextualize_chunk(record) == "Real heading\n\nBody"


def test_normalize_training_input_keeps_paragraph_breaks():
    raw = "Paragraph one.\n\nParagraph two.\n\n\n\nParagraph three."

    normalized = normalize_training_input(raw, max_chars=10_000)

    assert normalized == "Paragraph one.\n\nParagraph two.\n\nParagraph three."


def test_normalize_training_input_truncates_to_max_chars():
    raw = "A" * 5_000

    normalized = normalize_training_input(raw, max_chars=100)

    assert len(normalized) == 100


def test_document_text_from_chunk_records_contextualizes_and_joins_chunks():
    chunks = [
        ChunkRecord(text="Vendor: Acme GmbH.", headings=["Vendor information"]),
        ChunkRecord(text="Total: 1,234 EUR.", headings=["Totals"]),
    ]

    rendered = document_text_from_chunk_records(chunks, max_chars=10_000)

    assert rendered == (
        "Vendor information\n\nVendor: Acme GmbH.\n\nTotals\n\nTotal: 1,234 EUR."
    )


def test_document_text_from_chunk_records_skips_empty_chunks():
    chunks = [
        ChunkRecord(text="Body", headings=["Heading"]),
        ChunkRecord(text="   ", headings=[]),
    ]

    rendered = document_text_from_chunk_records(chunks, max_chars=10_000)

    assert rendered == "Heading\n\nBody"


@pytest.mark.asyncio
async def test_chunk_records_by_file_id_normalizes_stored_headings():
    result = MagicMock()
    result.all.return_value = [
        ("file-1", "Body", [" Heading ", "", 3, "Subheading"]),
        ("file-1", "Second", None),
        (None, "Skipped", ["Heading"]),
    ]
    db = AsyncMock()
    db.execute.return_value = result

    chunks = await ContentEnrichmentTrainingDatasetBuilder(db).chunk_records_by_file_id(
        ["file-1"]
    )

    assert chunks == {
        "file-1": [
            ChunkRecord(text="Body", headings=["Heading", "Subheading"]),
            ChunkRecord(text="Second", headings=[]),
        ]
    }
