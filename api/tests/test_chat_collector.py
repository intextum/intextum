"""Tests for request-scoped chat source collection."""

from chat.collector import ChatSourceCollector
from chat.sources import CollectedSource


def test_chat_source_collector_tracks_numbered_search_sources():
    """Search-source collection should assign citation numbers and preserve metadata."""
    collector = ChatSourceCollector()

    first = collector.add_search_source(
        file_path="documents/report.pdf",
        content_item_id="file-1",
        display_name="Report",
        content_kind=None,
        email_from_address=None,
        email_sent_at=None,
        parent_display_name=None,
        page_numbers=[1],
        doc_refs=["ref-1"],
        text="First quoted passage",
        image_urls=["/api/content/extracted-asset/file-1/page-1.png"],
    )
    second = collector.add_search_source(
        file_path="documents/manual.pdf",
        content_item_id="file-2",
        display_name="Manual",
        content_kind=None,
        email_from_address=None,
        email_sent_at=None,
        parent_display_name=None,
        page_numbers=[2],
        doc_refs=["ref-2"],
        text="Second quoted passage",
        image_urls=[],
    )

    assert (first, second) == (1, 2)
    assert collector.source_paths() == [
        "documents/report.pdf",
        "documents/manual.pdf",
    ]
    assert collector.sources[0] == CollectedSource(
        file_path="documents/report.pdf",
        content_item_id="file-1",
        display_name="Report",
        page_numbers=[1],
        doc_refs=["ref-1"],
        quote="First quoted passage",
        citation_index=1,
        image_urls=["/api/content/extracted-asset/file-1/page-1.png"],
    )


def test_chat_source_collector_builds_persisted_payloads():
    """Collected sources should serialize through one typed persistence boundary."""
    collector = ChatSourceCollector()
    collector.add_source(
        CollectedSource(
            file_path="documents/report.pdf",
            page_numbers=[1],
            doc_refs=["ref-1"],
            quote="Quoted text",
            citation_index="document",
            image_urls=["/api/content/extracted-asset/file-1/page-1.png"],
        )
    )

    assert collector.has_sources() is True
    assert collector.persisted_payloads() == [
        {
            "file_path": "documents/report.pdf",
            "display_name": "report.pdf",
            "title": "report.pdf",
            "page_numbers": [1],
            "doc_refs": ["ref-1"],
            "images": ["/api/content/extracted-asset/file-1/page-1.png"],
            "citation_index": "document",
            "quote": "Quoted text",
        }
    ]


def test_chat_source_collector_primes_context_sources_once_and_advances_numbering():
    """Preloaded report sources should keep stable citation numbers across the turn."""
    collector = ChatSourceCollector()

    primed = collector.prime_context_sources(
        key="report-1",
        sources=[
            CollectedSource(
                file_path="documents/report.pdf",
                page_numbers=[3],
                doc_refs=["ref-3"],
                quote="Quoted report source",
            ),
            CollectedSource(
                file_path="documents/appendix.pdf",
                page_numbers=[5],
                doc_refs=["ref-5"],
                quote="Another source",
                citation_index=7,
            ),
        ],
    )

    repeated = collector.prime_context_sources(
        key="report-1",
        sources=[
            CollectedSource(file_path="documents/report.pdf"),
        ],
    )
    next_search_citation = collector.add_search_source(
        file_path="documents/fresh.pdf",
        content_item_id="file-9",
        display_name="Fresh",
        content_kind=None,
        email_from_address=None,
        email_sent_at=None,
        parent_display_name=None,
        page_numbers=[9],
        doc_refs=["ref-9"],
        text="Fresh quote",
        image_urls=[],
    )

    assert [source.citation_index for source in primed] == [1, 7]
    assert repeated == primed
    assert next_search_citation == 8
