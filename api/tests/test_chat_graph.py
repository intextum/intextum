"""Tests for chat graph helper behavior."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from chat.collector import ChatSourceCollector
from chat.context import ChatContextScope
from chat.graph import (
    _latest_research_report_context,
    _messages_for_model,
    build_chat_graph,
)


def test_latest_research_report_context_uses_most_recent_report():
    context = _latest_research_report_context(
        [
            HumanMessage(content="First prompt"),
            AIMessage(
                content="Older report content",
                additional_kwargs={
                    "metadata": {"kind": "research_report", "title": "Older report"}
                },
            ),
            HumanMessage(content="Follow-up"),
            AIMessage(
                content="Newest report content",
                additional_kwargs={
                    "metadata": {"kind": "research_report", "title": "Newest report"}
                },
            ),
        ],
        source_collector=ChatSourceCollector(),
    )

    assert context is not None
    assert "Newest report" in context
    assert "Newest report content" in context
    assert "Older report content" not in context


def test_latest_research_report_context_ignores_non_report_messages():
    context = _latest_research_report_context(
        [
            HumanMessage(content="Prompt"),
            AIMessage(content="Plain assistant reply"),
        ],
        source_collector=ChatSourceCollector(),
    )

    assert context is None


def test_latest_research_report_context_primes_report_sources_for_follow_up_citations():
    collector = ChatSourceCollector()

    context = _latest_research_report_context(
        [
            HumanMessage(content="Prompt"),
            AIMessage(
                content="Research summary with grounded findings.",
                additional_kwargs={
                    "metadata": {
                        "kind": "research_report",
                        "title": "Grounded summary",
                        "report_id": "report-123",
                    },
                    "sources": [
                        {
                            "file_path": "documents/report.pdf",
                            "title": "Quarterly Report",
                            "page_numbers": [2, 3],
                            "doc_refs": ["ref-1"],
                            "citation_index": 1,
                            "quote": "A key supporting passage.",
                        }
                    ],
                },
            ),
        ],
        source_collector=collector,
    )

    assert context is not None
    assert "Report-backed sources:" in context
    assert "[1] Quarterly Report (pages 2, 3)" in context
    assert "cite the relevant report source markers inline" in context
    assert collector.persisted_payloads() == [
        {
            "file_path": "documents/report.pdf",
            "display_name": "report.pdf",
            "title": "Quarterly Report",
            "page_numbers": [2, 3],
            "doc_refs": ["ref-1"],
            "images": [],
            "citation_index": 1,
            "quote": "A key supporting passage.",
        }
    ]


def test_latest_research_report_context_prefers_relevant_sections_for_follow_up():
    collector = ChatSourceCollector()

    context = _latest_research_report_context(
        [
            HumanMessage(content="Please prepare a deep research report."),
            AIMessage(
                content=(
                    "# Retrofit Review\n\n"
                    "## Summary\n\nThe retrofit lowered energy demand by 12 percent [1].\n\n"
                    "## Recommendations\n\nPrioritize heating controls and insulation next [2]."
                ),
                additional_kwargs={
                    "metadata": {
                        "kind": "research_report",
                        "title": "Retrofit Review",
                        "report_id": "report-456",
                        "sections": [
                            {
                                "heading": "Summary",
                                "body": "The retrofit lowered energy demand by 12 percent [1].",
                            },
                            {
                                "heading": "Recommendations",
                                "body": "Prioritize heating controls and insulation next [2].",
                            },
                        ],
                    },
                    "sources": [
                        {
                            "file_path": "documents/summary.pdf",
                            "title": "Baseline Review",
                            "page_numbers": [2],
                            "doc_refs": ["summary-ref"],
                            "citation_index": 1,
                            "quote": "Energy demand fell after the retrofit.",
                        },
                        {
                            "file_path": "documents/recommendations.pdf",
                            "title": "Controls Roadmap",
                            "page_numbers": [7],
                            "doc_refs": ["recommendation-ref"],
                            "citation_index": 2,
                            "quote": "Heating controls and insulation should be prioritized next.",
                        },
                    ],
                },
            ),
            HumanMessage(
                content="What did the recommendations section say to do next?"
            ),
        ],
        source_collector=collector,
    )

    assert context is not None
    assert "prefer the most relevant report sections: Recommendations" in context
    assert "## Recommendations" in context
    assert "Prioritize heating controls and insulation next [2]." in context
    assert "## Summary" not in context
    assert "[2] Controls Roadmap (pages 7)" in context
    assert "[1] Baseline Review" not in context
    assert collector.persisted_payloads() == [
        {
            "file_path": "documents/recommendations.pdf",
            "display_name": "recommendations.pdf",
            "title": "Controls Roadmap",
            "page_numbers": [7],
            "doc_refs": ["recommendation-ref"],
            "images": [],
            "citation_index": 2,
            "quote": "Heating controls and insulation should be prioritized next.",
        }
    ]


def test_build_chat_graph_injects_context_file_enrichment_before_model_call():
    class _FakeModel:
        def __init__(self):
            self.messages = None

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            self.messages = messages
            return AIMessage(content="Structured answer")

    fake_model = _FakeModel()
    runtime = SimpleNamespace(
        settings=SimpleNamespace(
            CHAT_API_BASE="http://example.invalid/v1",
            CHAT_API_KEY="test-key",
            CHAT_MODEL="test-model",
            CHAT_SYSTEM_PROMPT="Base prompt.",
            CHAT_TOOL_PROMPT="Tool prompt.",
        ),
        source_collector=ChatSourceCollector(),
        db=AsyncMock(),
        user=SimpleNamespace(),
        context_scope=ChatContextScope(),
    )

    with (
        patch("chat.graph.core.ChatOpenAI", return_value=fake_model),
        patch(
            "chat.graph.core.build_context_file_enrichment_context",
            new=AsyncMock(return_value="Structured file context."),
        ),
    ):
        graph = build_chat_graph(runtime, checkpointer=None)
        asyncio.run(
            graph.ainvoke(
                {
                    "messages": [HumanMessage(content="What does the invoice say?")],
                    "context_file_paths": ["documents/invoice.pdf"],
                    "title": None,
                    "created_at": "2026-04-25T10:00:00+00:00",
                    "updated_at": "2026-04-25T10:00:00+00:00",
                    "user_sub": "sub-test",
                }
            )
        )

    assert fake_model.messages is not None
    system_messages = [
        message for message in fake_model.messages if isinstance(message, SystemMessage)
    ]
    assert len(system_messages) == 1
    assert "Base prompt." in system_messages[0].content
    assert (
        "Conversation history in this thread is part of the available context."
        in system_messages[0].content
    )
    assert "Structured file context." in system_messages[0].content
    assert isinstance(fake_model.messages[0], SystemMessage)
    assert not any(
        isinstance(message, SystemMessage) for message in fake_model.messages[1:]
    )


def test_messages_for_model_folds_existing_system_messages_to_front():
    messages = _messages_for_model(
        system_parts=["Base prompt.", "Context prompt."],
        conversation_messages=[
            HumanMessage(content="Hello"),
            SystemMessage(content="Legacy persisted system prompt."),
            AIMessage(content="Hi"),
        ],
    )

    assert len(messages) == 3
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == (
        "Base prompt.\n\nContext prompt.\n\nLegacy persisted system prompt."
    )
    assert [message.type for message in messages[1:]] == ["human", "ai"]
