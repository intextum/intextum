"""Focused tests for chat graph report-context helpers."""

from chat.graph.report_context import (
    _clip_text,
    _report_sections,
    _select_relevant_report_sections,
    _select_section_sources,
    _selected_section_context,
    _used_citation_indices,
)
from chat.sources import parse_stored_source_payloads


def test_used_citation_indices_preserves_order_and_deduplicates():
    """Citation parsing should preserve first-seen order without duplicates."""
    assert _used_citation_indices("See [2], [1], and again [2].") == [2, 1]


def test_report_sections_normalize_bodies_and_fallback_headings():
    """Section parsing should normalize bodies and fill blank headings."""
    sections = _report_sections(
        {
            "sections": [
                {
                    "heading": "  ",
                    "body": [{"text": "First finding [3]."}],
                },
                {
                    "heading": "Recommendations",
                    "body": "Prioritize controls [4].",
                },
                {"heading": "Ignored", "body": []},
                "skip",
            ]
        }
    )

    assert sections == [
        {
            "heading": "Section 1",
            "body": "First finding [3].",
            "citation_indices": [3],
        },
        {
            "heading": "Recommendations",
            "body": "Prioritize controls [4].",
            "citation_indices": [4],
        },
    ]


def test_select_relevant_report_sections_prefers_matching_follow_up():
    """Section ranking should prefer the most relevant report headings and bodies."""
    selected = _select_relevant_report_sections(
        report_sections=[
            {
                "heading": "Summary",
                "body": "The retrofit reduced demand by 12 percent.",
                "citation_indices": [],
            },
            {
                "heading": "Recommendations",
                "body": "Prioritize heating controls and insulation next.",
                "citation_indices": [],
            },
        ],
        follow_up_text="What did the recommendations section say to do next?",
    )

    assert [section["heading"] for section in selected] == ["Recommendations"]


def test_select_section_sources_uses_selected_citations_and_deduplicates():
    """Source selection should keep only cited sources and collapse duplicates."""
    sources = parse_stored_source_payloads(
        [
            {
                "file_path": "documents/summary.pdf",
                "title": "Summary",
                "citation_index": 1,
            },
            {
                "file_path": "documents/recommendations.pdf",
                "title": "Recommendations",
                "citation_index": 2,
            },
            {
                "file_path": "documents/recommendations.pdf",
                "title": "Recommendations",
                "citation_index": 2,
            },
        ]
    )

    selected = _select_section_sources(
        report_sources=sources,
        report_sections=[
            {
                "heading": "Recommendations",
                "body": "Act next [2].",
                "citation_indices": [2],
            }
        ],
    )

    assert [
        (source.file_path, source.title, source.citation_index) for source in selected
    ] == [("documents/recommendations.pdf", "Recommendations", 2)]


def test_selected_section_context_formats_headings_and_clips_text():
    """Selected section context should keep markdown headings and clip long text."""
    context = _selected_section_context(
        [
            {
                "heading": "Recommendations",
                "body": "Prioritize heating controls and insulation next.",
            }
        ]
    )

    assert (
        context
        == "## Recommendations\n\nPrioritize heating controls and insulation next."
    )
    assert _clip_text("abcdef", 5) == "ab..."
