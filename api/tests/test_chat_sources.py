"""Tests for typed persisted chat source payloads."""

from datetime import datetime

from chat.sources import (
    CollectedSource,
    StoredSourcePayload,
    build_source_payload,
    build_source_payloads,
    parse_source_payloads,
    parse_stored_source_payloads,
)
from models.content.items import ContentItemKind


def test_build_source_payload_uses_filename_title_fallback():
    """Collected sources should fall back to the filename when title is missing."""
    payload = build_source_payload(
        CollectedSource(
            file_path="documents/report.pdf",
            page_numbers=[1],
            doc_refs=["ref-1"],
            quote="Quoted text",
            citation_index=1,
            image_urls=["/api/content/extracted-asset/file/report.png"],
        )
    )

    assert payload == {
        "file_path": "documents/report.pdf",
        "display_name": "report.pdf",
        "title": "report.pdf",
        "page_numbers": [1],
        "doc_refs": ["ref-1"],
        "images": ["/api/content/extracted-asset/file/report.png"],
        "citation_index": 1,
        "quote": "Quoted text",
    }


def test_build_source_payloads_deduplicates_on_persisted_payload_key():
    """Duplicate collected citations should collapse using the stored payload key."""
    payloads = build_source_payloads(
        [
            CollectedSource(file_path="documents/report.pdf", citation_index=1),
            CollectedSource(file_path="documents/report.pdf", citation_index=1),
            CollectedSource(
                file_path="documents/report.pdf", citation_index="document"
            ),
            CollectedSource(file_path="", citation_index=2),
        ]
    )

    assert payloads == [
        StoredSourcePayload(
            file_path="documents/report.pdf",
            display_name="report.pdf",
            title="report.pdf",
            citation_index=1,
            quote="",
        ).to_message_payload(),
        StoredSourcePayload(
            file_path="documents/report.pdf",
            display_name="report.pdf",
            title="report.pdf",
            citation_index="document",
            quote="",
        ).to_message_payload(),
    ]


def test_parse_stored_source_payloads_filters_invalid_values_and_preserves_shape():
    """Persisted payload parsing should stay tolerant while keeping one typed shape."""
    raw_sources = [
        {
            "file_path": "documents/report.pdf",
            "title": "Quarterly Report",
            "page_numbers": [1, "2", 3],
            "doc_refs": ["ref-1", 2],
            "images": ["page-1.png", None],
            "citation_index": 7,
            "quote": "Quoted text",
            "ignored": "value",
        },
        {
            "file_path": "documents/manual.pdf",
            "citation_index": "document",
            "page_numbers": ["bad"],
            "doc_refs": [3],
            "images": [4],
            "quote": "",
        },
        {"title": "missing path"},
        "not-a-dict",
    ]

    payloads = parse_stored_source_payloads(raw_sources)

    assert payloads == [
        StoredSourcePayload(
            file_path="documents/report.pdf",
            title="Quarterly Report",
            page_numbers=[1, 3],
            doc_refs=["ref-1"],
            images=["page-1.png"],
            citation_index=7,
            quote="Quoted text",
        ),
        StoredSourcePayload(
            file_path="documents/manual.pdf",
            title=None,
            page_numbers=[],
            doc_refs=[],
            images=[],
            citation_index="document",
            quote="",
        ),
    ]

    assert parse_source_payloads(raw_sources) == [
        payloads[0].to_conversation_source(),
        payloads[1].to_conversation_source(),
    ]
    assert parse_source_payloads(raw_sources)[1].citation_index is None


def test_stored_source_payload_round_trips_to_collected_source():
    payload = StoredSourcePayload(
        file_path="documents/report.pdf",
        title="Quarterly Report",
        page_numbers=[1, 3],
        doc_refs=["ref-1"],
        images=["page-1.png"],
        citation_index=4,
        quote="Quoted text",
    )

    collected = payload.to_collected_source()

    assert collected == CollectedSource(
        file_path="documents/report.pdf",
        title="Quarterly Report",
        page_numbers=[1, 3],
        doc_refs=["ref-1"],
        image_urls=["page-1.png"],
        citation_index=4,
        quote="Quoted text",
    )


def test_reviewed_enrichment_source_kind_round_trips():
    payload = build_source_payload(
        CollectedSource(
            file_path="documents/invoice.pdf",
            title="Reviewed enrichment evidence: Field invoice_number",
            display_name="invoice.pdf",
            content_kind=ContentItemKind.FILE,
            source_kind="reviewed_enrichment",
            page_numbers=[1],
            doc_refs=["#/texts/4"],
            citation_index=2,
            quote="RE-2026-42",
        )
    )

    assert payload["source_kind"] == "reviewed_enrichment"
    parsed = parse_stored_source_payloads([payload])
    assert parsed == [
        StoredSourcePayload(
            file_path="documents/invoice.pdf",
            display_name="invoice.pdf",
            content_kind=ContentItemKind.FILE,
            title="Reviewed enrichment evidence: Field invoice_number",
            source_kind="reviewed_enrichment",
            page_numbers=[1],
            doc_refs=["#/texts/4"],
            images=[],
            citation_index=2,
            quote="RE-2026-42",
        )
    ]
    assert parsed[0].to_conversation_source().source_kind == "reviewed_enrichment"


def test_email_source_metadata_round_trips():
    payload = build_source_payload(
        CollectedSource(
            file_path="mailbox/Inbox/message.eml",
            display_name="Quarterly update",
            content_kind=ContentItemKind.EMAIL_MESSAGE,
            email_from_address="alice@example.com",
            email_sent_at=datetime(2026, 4, 27, 10, 0, 0),
            page_numbers=[1],
            doc_refs=["#/texts/2"],
            citation_index=4,
            quote="Hello team",
        )
    )

    assert payload["email_from_address"] == "alice@example.com"
    assert payload["email_sent_at"] == "2026-04-27T10:00:00"
    parsed = parse_stored_source_payloads([payload])
    assert parsed[0].email_from_address == "alice@example.com"
    assert parsed[0].email_sent_at == datetime(2026, 4, 27, 10, 0, 0)
