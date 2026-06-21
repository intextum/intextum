"""Focused tests for research graph output helpers."""

from research.graph.output import (
    _compose_markdown,
    _select_images,
    _used_citation_indices,
)


def test_used_citation_indices_preserves_order_and_deduplicates():
    """Citation parsing should preserve first-seen order without duplicates."""
    assert _used_citation_indices("See [2], [1], and again [2].") == [2, 1]


def test_select_images_uses_referenced_citations_and_deduplicates_urls():
    """Image selection should only use cited sources and should deduplicate URLs."""
    images = _select_images(
        sections=[
            {"heading": "Summary", "body": "Use the emissions chart [2]."},
            {"heading": "Recommendations", "body": "No image here."},
        ],
        sources=[
            {
                "citation_index": 1,
                "title": "Program",
                "images": ["ignored.png"],
            },
            {
                "citation_index": 2,
                "title": "Roadmap",
                "images": ["chart.png", "chart.png", "diagram.png"],
            },
        ],
    )

    assert images == [
        {"url": "chart.png", "title": "Roadmap", "citation_index": 2},
        {"url": "diagram.png", "title": "Roadmap", "citation_index": 2},
    ]


def test_compose_markdown_includes_sections_and_sources():
    """Markdown composition should render headings and formatted sources."""
    markdown = _compose_markdown(
        title="Program Review",
        sections=[
            {"heading": "Summary", "body": "The retrofit reduced emissions. [1]"},
            {"heading": "Recommendations", "body": "Prioritize roadmap actions. [2]"},
        ],
        sources=[
            {
                "citation_index": 1,
                "title": "Program Report",
                "file_path": "docs/program.pdf",
                "page_numbers": [3],
            },
            {
                "citation_index": 2,
                "file_path": "docs/roadmap.pdf",
                "page_numbers": [],
            },
        ],
    )

    assert "# Program Review" in markdown
    assert "## Summary" in markdown
    assert "## Recommendations" in markdown
    assert "## Sources" in markdown
    assert "- [1] Program Report: `docs/program.pdf` (pages 3)" in markdown
    assert "- [2] roadmap.pdf: `docs/roadmap.pdf`" in markdown
