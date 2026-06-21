"""Focused tests for research graph LLM helper functions."""

from types import SimpleNamespace

from research.graph.llm import (
    _extract_json_object,
    _response_text,
    _strip_code_fences,
)


def test_strip_code_fences_and_extract_json_object_from_wrapped_response():
    """JSON extraction should tolerate fenced and surrounded model output."""
    wrapped = """
    ```json
    {"title": "Program Review", "outline": ["Summary"]}
    ```
    """
    assert (
        _strip_code_fences(wrapped)
        == '{"title": "Program Review", "outline": ["Summary"]}'
    )
    assert _extract_json_object("Response:\n" + wrapped) == {
        "title": "Program Review",
        "outline": ["Summary"],
    }


def test_response_text_flattens_mixed_content_payloads():
    """Response text normalization should flatten string, dict, and object chunks."""
    response = SimpleNamespace(
        content=[
            "First line",
            {"text": "Second line"},
            SimpleNamespace(text="Third line"),
            {"ignored": "value"},
        ]
    )

    assert _response_text(response) == "First line\nSecond line\nThird line"
