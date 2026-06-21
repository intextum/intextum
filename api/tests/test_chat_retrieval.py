"""Tests for typed chat-side vector-search chunk adapters."""

from chat.retrieval import RetrievedChunk, parse_retrieved_chunks
from models.vector import VectorDocumentChunk, VectorSearchHit


def test_parse_retrieved_chunks_filters_invalid_items_and_normalizes_fields():
    """Raw vector payloads should collapse into one tolerant internal chunk shape."""
    chunks = parse_retrieved_chunks(
        [
            {
                "text": "Example",
                "file_path": "report.pdf",
                "folder_uuid": "folder-docs",
                "content_item_id": "file-1",
                "page_numbers": [1, "2", 3],
                "doc_refs": ["ref-1", 2],
                "images": ["figures/page-1.png", None],
            },
            {
                "text": 7,
                "file_path": None,
                "folder_uuid": 3,
            },
            "not-a-dict",
        ]
    )

    assert chunks == [
        RetrievedChunk(
            text="Example",
            score=None,
            file_path="report.pdf",
            folder_uuid="folder-docs",
            content_item_id="file-1",
            display_name="report.pdf",
            page_numbers=[1, 3],
            doc_refs=["ref-1"],
            images=["figures/page-1.png"],
        ),
        RetrievedChunk(
            text="",
            score=None,
            file_path="unknown",
            folder_uuid="",
            content_item_id="",
            page_numbers=[],
            doc_refs=[],
            images=[],
        ),
    ]


def test_retrieved_chunk_derives_paths_and_image_urls():
    """Chunk helpers should centralize the tool-facing path and asset URL logic."""
    chunk = RetrievedChunk(
        file_path="reports/quarterly.pdf",
        folder_uuid="folder-docs",
        content_item_id="file-1",
        images=["figures/page-1.png", "page-1.png", "page-2.png"],
    )

    assert chunk.resolved_file_path({"folder-docs": "documents"}) == (
        "documents/reports/quarterly.pdf"
    )
    assert chunk.image_urls() == [
        "/api/content/extracted-asset/file-1/page-1.png",
        "/api/content/extracted-asset/file-1/page-2.png",
    ]


def test_parse_retrieved_chunks_accepts_typed_vector_models():
    """Typed vector models should feed the chat tool adapter without re-shaping."""
    chunks = parse_retrieved_chunks(
        [
            VectorSearchHit(
                score=0.91,
                file_path="reports/quarterly.pdf",
                folder_uuid="folder-docs",
                content_item_id="file-1",
                text="Quarterly summary",
                page_numbers=[4],
                doc_refs=["ref-1"],
                images=["figures/chart.png"],
            ),
            VectorDocumentChunk(
                file_path="reports/quarterly.pdf",
                content_item_id="file-1",
                text="Appendix",
                page_numbers=[7],
                images=["appendix.png"],
            ),
        ]
    )

    assert chunks == [
        RetrievedChunk(
            text="Quarterly summary",
            score=0.91,
            file_path="reports/quarterly.pdf",
            folder_uuid="folder-docs",
            content_item_id="file-1",
            display_name="quarterly.pdf",
            page_numbers=[4],
            doc_refs=["ref-1"],
            images=["figures/chart.png"],
        ),
        RetrievedChunk(
            text="Appendix",
            score=None,
            file_path="reports/quarterly.pdf",
            folder_uuid="",
            content_item_id="file-1",
            display_name="quarterly.pdf",
            page_numbers=[7],
            doc_refs=[],
            images=["appendix.png"],
        ),
    ]


def test_parse_retrieved_chunks_preserves_numeric_score_from_dict_payload():
    """Raw dict payloads should keep semantic similarity when present."""
    chunks = parse_retrieved_chunks(
        [
            {
                "text": "Heat pump guidance",
                "score": 0.87,
                "file_path": "roadmap.pdf",
                "content_item_id": "file-1",
            }
        ]
    )

    assert chunks == [
        RetrievedChunk(
            text="Heat pump guidance",
            score=0.87,
            file_path="roadmap.pdf",
            folder_uuid="",
            content_item_id="file-1",
            display_name="roadmap.pdf",
            page_numbers=[],
            doc_refs=[],
            images=[],
        )
    ]
