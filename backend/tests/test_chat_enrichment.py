"""Tests for prompt-time file enrichment context in chat."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat.collector import ChatSourceCollector
from chat.context import ChatContextScope
from chat.enrichment import build_context_file_enrichment_context
from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem
from models.user import User


def _db_with_records(records):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = records
    db.execute.return_value = result
    return db


def _context_scope() -> ChatContextScope:
    return ChatContextScope(
        raw_paths=["documents/invoice.pdf"],
        constraints=[("documents/invoice.pdf", "folder-documents", "invoice.pdf")],
        folder_name_to_uuid={"documents": "folder-documents"},
        folder_uuid_to_name={"folder-documents": "documents"},
        file_ids=["file-1"],
    )


@pytest.mark.asyncio
async def test_build_context_file_enrichment_context_includes_effective_values():
    record = IndexedContentItem(content_item_id="file-1")
    record.enrichment_state = ContentItemEnrichmentState(
        content_item_id="file-1",
        classification_system_label="Permit",
        classification_override_label="Invoice",
        classification_effective_label="Invoice",
        classification_review_status="corrected",
        classification_reviewed_by="Editor",
        classification_review_history_json=[],
        classification_evidence_json=[
            {
                "chunk_index": 0,
                "page_numbers": [1],
                "doc_refs": ["#/texts/1"],
                "snippet": "Invoice document with number RE-2026-0042.",
            }
        ],
        extraction_data_json={
            "invoice_number": "RE-2026-0042",
            "gross_amount": 119.0,
        },
        extraction_effective_data_json={
            "invoice_number": "RE-2026-0042",
            "gross_amount": 119.0,
            "vat_amount": 19.0,
        },
        extraction_fields_json={
            "invoice_number": {
                "value": "RE-2026-0042",
                "dtype": "str",
                "required": True,
                "evidence": [
                    {
                        "chunk_index": 1,
                        "page_numbers": [1],
                        "doc_refs": ["#/texts/2"],
                        "snippet": "Rechnungsnummer RE-2026-0042",
                    }
                ],
                "candidate_values": ["RE-2026-0042"],
                "conflict": False,
            },
            "gross_amount": {
                "value": 119.0,
                "dtype": "float",
                "required": False,
                "evidence": [
                    {
                        "chunk_index": 2,
                        "page_numbers": [1],
                        "doc_refs": ["#/tables/1"],
                        "snippet": "Gesamtbetrag 119,00 EUR",
                    }
                ],
                "candidate_values": [119.0],
                "conflict": False,
            },
        },
        extraction_override_data_json={"vat_amount": 19.0},
        extraction_review_status="accepted",
        extraction_reviewed_by="Reviewer",
        extraction_review_history_json=[],
    )

    collector = ChatSourceCollector()
    context = await build_context_file_enrichment_context(
        db=_db_with_records([record]),
        user=User(username="writer", sub="sub-writer"),
        context_scope=_context_scope(),
        source_collector=collector,
    )

    assert context is not None
    assert "documents/invoice.pdf" in context
    assert (
        "Document class: Invoice (user correction, human-reviewed corrected)" in context
    )
    assert "invoice_number: RE-2026-0042" in context
    assert "gross_amount: 119.0" in context
    assert "vat_amount: 19.0" in context
    assert "Extracted fields (user correction, human-reviewed accepted):" in context
    assert "Reviewed enrichment evidence sources:" in context
    assert (
        "[1] Document class: Invoice (pages 1; refs #/texts/1): Invoice document with number RE-2026-0042."
        in context
    )
    assert (
        "[2] Field invoice_number (pages 1; refs #/texts/2): Rechnungsnummer RE-2026-0042"
        in context
    )
    assert "Human-reviewed accepted or corrected enrichment is stronger" in context
    assert "reviewed enrichment evidence snippets are grounded support" in context
    assert "prefer the underlying document content" in context
    assert (
        "cite retrieved document, report, or reviewed enrichment evidence source markers inline"
        in context
    )
    assert collector.persisted_payloads() == [
        {
            "file_path": "documents/invoice.pdf",
            "title": "Reviewed enrichment evidence: Document class: Invoice",
            "display_name": "Reviewed enrichment evidence: Document class: Invoice",
            "content_kind": "file",
            "source_kind": "reviewed_enrichment",
            "page_numbers": [1],
            "doc_refs": ["#/texts/1"],
            "images": [],
            "citation_index": 1,
            "quote": "Invoice document with number RE-2026-0042.",
        },
        {
            "file_path": "documents/invoice.pdf",
            "title": "Reviewed enrichment evidence: Field invoice_number",
            "display_name": "Reviewed enrichment evidence: Field invoice_number",
            "content_kind": "file",
            "source_kind": "reviewed_enrichment",
            "page_numbers": [1],
            "doc_refs": ["#/texts/2"],
            "images": [],
            "citation_index": 2,
            "quote": "Rechnungsnummer RE-2026-0042",
        },
        {
            "file_path": "documents/invoice.pdf",
            "title": "Reviewed enrichment evidence: Field gross_amount",
            "display_name": "Reviewed enrichment evidence: Field gross_amount",
            "content_kind": "file",
            "source_kind": "reviewed_enrichment",
            "page_numbers": [1],
            "doc_refs": ["#/tables/1"],
            "images": [],
            "citation_index": 3,
            "quote": "Gesamtbetrag 119,00 EUR",
        },
    ]


@pytest.mark.asyncio
async def test_build_context_file_enrichment_context_returns_none_without_data():
    record = IndexedContentItem(content_item_id="file-1")

    context = await build_context_file_enrichment_context(
        db=_db_with_records([record]),
        user=User(username="writer", sub="sub-writer"),
        context_scope=_context_scope(),
    )

    assert context is None
