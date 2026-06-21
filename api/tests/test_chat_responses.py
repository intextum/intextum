"""Tests for assistant-response finalization helpers."""

from langchain_core.messages import AIMessage

from chat.collector import ChatSourceCollector
from chat.responses import finalize_assistant_response
from chat.sources import CollectedSource


def test_finalize_assistant_response_attaches_created_at_and_sources():
    """Visible assistant replies should carry timestamp and persisted citations."""
    collector = ChatSourceCollector(
        sources=[
            CollectedSource(
                file_path="documents/report.pdf",
                page_numbers=[1],
                doc_refs=["ref-1"],
                quote="Quoted text",
                citation_index=1,
                image_urls=["/api/content/extracted-asset/file-1/page-1.png"],
            )
        ]
    )
    response = AIMessage(content="Answer", id="ai-1")

    finalized = finalize_assistant_response(
        response,
        source_collector=collector,
        created_at="2026-04-21T18:00:00+00:00",
    )

    assert finalized is not response
    assert finalized.additional_kwargs == {
        "created_at": "2026-04-21T18:00:00+00:00",
        "sources": [
            {
                "file_path": "documents/report.pdf",
                "display_name": "report.pdf",
                "title": "report.pdf",
                "page_numbers": [1],
                "doc_refs": ["ref-1"],
                "images": ["/api/content/extracted-asset/file-1/page-1.png"],
                "citation_index": 1,
                "quote": "Quoted text",
            }
        ],
    }


def test_finalize_assistant_response_leaves_tool_call_messages_unchanged():
    """Tool-call messages should not be decorated with visible-response metadata."""
    response = AIMessage(
        content="Tool call",
        tool_calls=[
            {
                "name": "search_documents",
                "args": {},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )

    finalized = finalize_assistant_response(
        response,
        source_collector=ChatSourceCollector(),
        created_at="2026-04-21T18:00:00+00:00",
    )

    assert finalized is response
