"""Focused tests for assistant-response export helpers."""

from io import BytesIO
from zipfile import ZipFile

from models.exports import AssistantResponseExportRequest
from services.exports import build_docx_export
from services.exports_docx_markdown import _inline_runs, _markdown_to_docx_paragraphs


def test_inline_runs_preserve_links_and_strip_inline_formatting():
    """Inline markdown should collapse formatting but preserve hyperlink targets."""
    runs = _inline_runs(
        "See **[Program Report](https://example.com/report)** and `notes`."
    )

    assert [(run.text, run.hyperlink_url) for run in runs] == [
        ("See ", None),
        ("Program Report", "https://example.com/report"),
        (" and notes.", None),
    ]


def test_markdown_to_docx_paragraphs_adds_title_and_normalizes_blocks():
    """Markdown conversion should synthesize a title and normalize list/image blocks."""
    paragraphs = _markdown_to_docx_paragraphs(
        "Summary paragraph.\n\n- First bullet\n1. Ordered item\n\n![Site Plan](https://example.com/site-plan.png)",
        title="Export Title",
    )

    assert [
        (paragraph.kind, paragraph.text, paragraph.image_url)
        for paragraph in paragraphs
    ] == [
        ("heading1", "Export Title", None),
        ("paragraph", "Summary paragraph.", None),
        ("bullet", "• First bullet", None),
        ("numbered", "1. Ordered item", None),
        ("image", "Site Plan", "https://example.com/site-plan.png"),
    ]


def test_markdown_to_docx_paragraphs_converts_markdown_tables():
    """Markdown pipe tables should become typed DOCX table blocks."""
    paragraphs = _markdown_to_docx_paragraphs(
        "\n".join(
            [
                "# Materials",
                "",
                "| Material | Count |",
                "| --- | ---: |",
                "| **Oak** | 2 |",
                "| [Pine](https://example.com/pine) | 4 |",
            ]
        ),
        title="Fallback",
    )

    assert paragraphs[0].kind == "heading1"
    assert paragraphs[1].kind == "table"
    assert paragraphs[1].table_rows == (
        ("Material", "Count"),
        ("Oak", "2"),
        ("[Pine](https://example.com/pine)", "4"),
    )


def test_build_docx_export_writes_expected_archive_parts():
    """DOCX export should render document XML and hyperlink relationships."""
    payload = AssistantResponseExportRequest.model_validate(
        {
            "title": "Retrofit Review",
            "filename_base": "retrofit-review",
            "markdown": "# Retrofit Review\n\nSee [Program Report](https://example.com/report).",
            "embedded_images": [],
        }
    )

    archive_bytes = build_docx_export(payload)

    with ZipFile(BytesIO(archive_bytes)) as archive:
        names = set(archive.namelist())
        document_xml = archive.read("word/document.xml").decode("utf-8")
        relationships_xml = archive.read("word/_rels/document.xml.rels").decode("utf-8")
        content_types_xml = archive.read("[Content_Types].xml").decode("utf-8")

    assert "[Content_Types].xml" in names
    assert "word/document.xml" in names
    assert "word/_rels/document.xml.rels" in names
    assert "Retrofit Review" in document_xml
    assert "Program Report" in document_xml
    assert "https://example.com/report" in relationships_xml
    assert "wordprocessingml.document.main+xml" in content_types_xml


def test_build_docx_export_renders_markdown_tables_as_word_tables():
    """DOCX export should emit Word table XML rather than raw markdown pipes."""
    payload = AssistantResponseExportRequest.model_validate(
        {
            "title": "Material Report",
            "filename_base": "material-report",
            "markdown": (
                "# Material Report\n\n"
                "| Material | Source |\n"
                "| --- | --- |\n"
                "| Oak | [Catalog](https://example.com/catalog) |"
            ),
            "embedded_images": [],
        }
    )

    archive_bytes = build_docx_export(payload)

    with ZipFile(BytesIO(archive_bytes)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        relationships_xml = archive.read("word/_rels/document.xml.rels").decode("utf-8")

    assert "<w:tbl>" in document_xml
    assert "<w:tr>" in document_xml
    assert "<w:tc>" in document_xml
    assert "Material" in document_xml
    assert "Catalog" in document_xml
    assert "| Material | Source |" not in document_xml
    assert "https://example.com/catalog" in relationships_xml
