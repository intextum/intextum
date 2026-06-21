"""Focused tests for structured-fact helpers in the research graph."""

from research.graph.structured import (
    _relevant_structured_facts,
    _structured_facts_block,
)


def test_relevant_structured_facts_prefers_reviewed_matching_items():
    """Structured fact ranking should prefer reviewed facts that match the section ask."""
    facts = [
        {
            "api_path": "documents/overview.pdf",
            "document_class": "Overview",
            "extraction_data": {"status": "archived"},
        },
        {
            "api_path": "documents/invoice.pdf",
            "document_class": "Invoice",
            "document_class_review_status": "corrected",
            "extraction_review_status": "accepted",
            "extraction_data": {
                "invoice_number": "RE-2026-42",
                "gross_amount": 119.0,
            },
        },
    ]

    selected = _relevant_structured_facts(
        structured_facts=facts,
        prompt="Review the invoice package.",
        heading="Payment Details",
        question="Which invoice identifiers and amounts matter most?",
    )

    assert selected == [facts[1]]


def test_structured_facts_block_formats_reviewed_evidence_and_metadata():
    """Structured fact blocks should render metadata labels and reviewed snippets."""
    block = _structured_facts_block(
        structured_facts=[
            {
                "api_path": "documents/invoice.pdf",
                "document_class": "Invoice",
                "document_class_source": "user_override",
                "document_class_review_status": "corrected",
                "extraction_data": {
                    "invoice_number": "RE-2026-42",
                    "gross_amount": 119.0,
                },
                "extraction_source": "document_processing",
                "extraction_review_status": "accepted",
                "reviewed_evidence": [
                    {
                        "label": "Field invoice_number",
                        "snippet": "Rechnungsnummer RE-2026-42",
                        "page_numbers": [1],
                        "doc_refs": ["#/texts/4"],
                    }
                ],
            }
        ],
        prompt="Summarize the invoice payment details.",
        heading="Payment Details",
        question="Which invoice identifiers matter?",
    )

    assert "File: documents/invoice.pdf" in block
    assert (
        "Document class: Invoice (user correction, human-reviewed corrected)" in block
    )
    assert "Extracted fields (document processing, human-reviewed accepted):" in block
    assert "invoice_number: RE-2026-42" in block
    assert "Reviewed enrichment evidence snippets:" in block
    assert (
        "Field invoice_number (pages 1; refs #/texts/4): Rechnungsnummer RE-2026-42"
        in block
    )
