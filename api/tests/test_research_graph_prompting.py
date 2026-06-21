"""Focused tests for research graph prompting helpers."""

from research.graph.prompting import (
    _section_plans,
    _section_query_candidates,
)


def test_section_plans_reuse_last_question_and_default_outline():
    """Section planning should fall back cleanly when outline/questions are sparse."""
    plans = _section_plans(
        {
            "prompt": "Assess the sustainability program.",
            "outline": ["Summary", "Recommendations", "Risks"],
            "questions": ["What changed?", "What next?"],
        }
    )

    assert plans == [
        {"heading": "Summary", "question": "What changed?"},
        {"heading": "Recommendations", "question": "What next?"},
        {"heading": "Risks", "question": "What next?"},
    ]

    fallback_plans = _section_plans(
        {
            "prompt": " Assess the sustainability program. ",
            "outline": [],
            "questions": [],
        }
    )

    assert fallback_plans == [
        {
            "heading": "Executive Summary",
            "question": "Assess the sustainability program.",
        },
        {
            "heading": "Findings",
            "question": "Assess the sustainability program.",
        },
        {
            "heading": "Recommendations",
            "question": "Assess the sustainability program.",
        },
    ]


def test_section_query_candidates_deduplicate_and_cap_results():
    """Query candidates should normalize duplicates and stop at the configured cap."""
    candidates = _section_query_candidates(
        prompt="Assess retrofit priorities.",
        heading="Recommendations",
        question="Recommendations",
    )

    assert candidates == [
        "Assess retrofit priorities. Section focus: Recommendations",
        "Recommendations: Recommendations",
        "Recommendations",
    ]
