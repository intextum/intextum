"""Focused tests for worker-side content enrichment utilities."""

from types import SimpleNamespace

from intextum_worker.models import (
    WorkerDocumentEvidence,
    WorkerDocumentExtractionSchema,
)
from intextum_worker.services.content_enrichment_utils import (
    MAX_EXTRACTION_WINDOWS,
    _build_chunk_evidence,
    _coerce_field_value,
    _compact_blank_lines,
    _extraction_window_text,
    _find_local_evidence_for_terms,
    _find_local_evidence_for_value,
    _iter_extraction_windows,
    _pick_schema,
    _select_list_field_result,
    _select_scalar_field_result,
)


def _chunk(text: str, *, page_numbers=None, self_ref=None, image_uri=None):
    """Build a lightweight Docling-like chunk test double."""
    prov = [SimpleNamespace(page_no=page_no) for page_no in (page_numbers or [])]
    doc_item = SimpleNamespace(
        prov=prov,
        self_ref=self_ref,
        image=SimpleNamespace(uri=image_uri) if image_uri else None,
    )
    meta = SimpleNamespace(doc_items=[doc_item])
    return SimpleNamespace(text=text, meta=meta)


def test_build_chunk_evidence_collects_doc_metadata():
    chunk = _chunk(
        "  Permit issued by Landkreis.  ",
        page_numbers=[2, 1, 2],
        self_ref="#/pages/1",
        image_uri="images/page-1.png",
    )

    evidence = _build_chunk_evidence(chunk, 3)

    assert evidence is not None
    assert evidence.chunk_index == 3
    assert evidence.page_numbers == [1, 2]
    assert evidence.doc_refs == ["#/pages/1"]
    assert evidence.images == ["images/page-1.png"]
    assert evidence.snippet == "Permit issued by Landkreis."


def test_find_local_evidence_for_terms_skips_empty_chunks_and_limits_results():
    chunks = [
        _chunk("First"),
        _chunk("   "),
        _chunk("Second"),
    ]

    evidence = _find_local_evidence_for_terms(
        chunks,
        ["first", "second"],
        max_items=1,
    )

    assert len(evidence) == 1
    assert evidence[0].chunk_index == 0
    assert evidence[0].snippet == "First"


def test_find_local_evidence_for_value_matches_list_items_case_insensitively():
    chunks = [
        _chunk("Invoice INV-42"),
        _chunk("Customer C-100"),
    ]

    evidence = _find_local_evidence_for_value(chunks, ["inv-42", "c-100"])

    assert [item.chunk_index for item in evidence] == [0, 1]


def test_iter_extraction_windows_caps_non_empty_chunk_windows():
    chunks = [_chunk(f"Chunk {index}") for index in range(MAX_EXTRACTION_WINDOWS + 3)]

    windows = _iter_extraction_windows(chunks, fallback_text="Fallback")

    assert len(windows) == MAX_EXTRACTION_WINDOWS
    assert windows[0][0] == "Chunk 0"
    assert windows[0][1] is not None
    assert windows[0][1].chunk_index == 0
    assert windows[-1][0] == f"Chunk {MAX_EXTRACTION_WINDOWS - 1}"


def test_iter_extraction_windows_uses_document_fallback_without_chunks():
    windows = _iter_extraction_windows(None, fallback_text=" Full document text ")

    assert len(windows) == 1
    assert windows[0][0] == "Full document text"
    assert windows[0][1] is not None
    assert windows[0][1].chunk_index is None


def test_compact_blank_lines_preserves_paragraph_breaks_and_strips_runs():
    raw = "First line  \n  \n\nSecond paragraph\n\n\n\nThird"

    assert _compact_blank_lines(raw) == "First line\n\nSecond paragraph\n\nThird"


def test_extraction_window_text_prepends_headings_and_captions():
    chunk = SimpleNamespace(
        text="Body text with details.",
        meta=SimpleNamespace(
            headings=["Section A", "Subsection 1"],
            captions=["Table 1: line items"],
            doc_items=[],
        ),
    )

    rendered = _extraction_window_text(chunk, max_chars=10_000)

    assert rendered == (
        "Section A\nSubsection 1\n\nTable 1: line items\n\nBody text with details."
    )


def test_extraction_window_text_reads_top_level_headings_for_rerun_chunks():
    """SimpleChunk-style chunks expose headings directly (meta is None)."""
    chunk = SimpleNamespace(
        text="Body",
        meta=None,
        headings=["Vendor information"],
        captions=[],
    )

    rendered = _extraction_window_text(chunk, max_chars=10_000)

    assert rendered == "Vendor information\n\nBody"


def test_extraction_window_text_renders_table_items_as_markdown():
    class _FakeDataFrame:
        def to_markdown(self, index: bool = False) -> str:
            return "| col |\n|-----|\n| val |"

    class _FakeTable:
        def export_to_dataframe(self) -> "_FakeDataFrame":
            return _FakeDataFrame()

    # Stand in for TableItem so the isinstance check passes via runtime import shim.
    import intextum_worker.services.content_enrichment_utils as utils_module

    fake_table = _FakeTable()
    chunk = SimpleNamespace(
        text="Original flattened table text",
        meta=SimpleNamespace(headings=["Invoice"], captions=[], doc_items=[fake_table]),
    )

    original_check = utils_module._is_docling_table_item
    utils_module._is_docling_table_item = lambda item: item is fake_table
    try:
        rendered = _extraction_window_text(chunk, max_chars=10_000)
    finally:
        utils_module._is_docling_table_item = original_check

    assert "| col |" in rendered
    assert "Original flattened table text" in rendered
    assert rendered.startswith("Invoice")


def test_extraction_window_text_truncates_to_max_chars():
    chunk = SimpleNamespace(text="A" * 5_000, meta=None)

    rendered = _extraction_window_text(chunk, max_chars=100)

    assert len(rendered) == 100


def test_pick_schema_prefers_matching_document_class():
    permit_schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "name": "permit_core",
            "document_class": "Permit",
            "fields": [],
        }
    )
    invoice_schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "name": "invoice_core",
            "document_class": "Invoice",
            "fields": [],
        }
    )

    schema = _pick_schema(
        [invoice_schema, permit_schema],
        document_class="Permit",
    )

    assert schema is permit_schema


def test_pick_schema_does_not_use_single_schema_fallback_for_different_class():
    invoice_schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "name": "invoice_core",
            "document_class": "Invoice",
            "fields": [],
        }
    )

    schema = _pick_schema(
        [invoice_schema],
        document_class="Application",
    )

    assert schema is None


def test_pick_schema_requires_selected_class_even_with_single_schema():
    invoice_schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "name": "invoice_core",
            "document_class": "Invoice",
            "fields": [],
        }
    )

    schema = _pick_schema(
        [invoice_schema],
        document_class=None,
    )

    assert schema is None


def test_coerce_field_value_handles_common_dtype_conversions():
    assert _coerce_field_value(" ja ", dtype="bool") is True
    assert _coerce_field_value(" 42 ", dtype="int") == 42
    assert _coerce_field_value("1.234,56", dtype="float") == 1234.56
    assert _coerce_field_value(["A", "", None, "B"], dtype="list") == ["A", "B"]
    assert _coerce_field_value("29.04.2026", dtype="date") == "2026-04-29"
    assert _coerce_field_value("1.234,56 EUR", dtype="currency") == {
        "amount": 1234.56,
        "currency": "EUR",
    }


def test_select_scalar_field_result_deduplicates_candidates_without_singleton_conflicts():
    evidence_a = WorkerDocumentEvidence(snippet="A")
    evidence_b = WorkerDocumentEvidence(snippet="B")

    result = _select_scalar_field_result(
        [
            ("Landkreis", evidence_a, 0.8),
            ("landkreis", evidence_b, 0.7),
            ("Stadt", None, 0.2),
        ],
        dtype="str",
        required=True,
    )

    assert result is not None
    assert result.value == "Landkreis"
    assert result.conflict is False
    assert result.candidate_values == [
        {
            "value": "Landkreis",
            "confidence": 0.8,
            "evidence": [
                {
                    "snippet": "A",
                    "page_numbers": [],
                    "doc_refs": [],
                    "images": [],
                    "matched_queries": [],
                },
                {
                    "snippet": "B",
                    "page_numbers": [],
                    "doc_refs": [],
                    "images": [],
                    "matched_queries": [],
                },
            ],
        },
        {"value": "Stadt", "confidence": 0.2, "evidence": []},
    ]
    assert result.evidence == [evidence_a, evidence_b]
    assert result.confidence == 0.8


def test_select_scalar_field_result_ignores_singleton_alternates_as_conflicts():
    evidence = WorkerDocumentEvidence(snippet="A")

    result = _select_scalar_field_result(
        [
            ("2026-04-29", evidence, None),
            ("29.04.2026", None, None),
        ],
        dtype="str",
        required=False,
    )

    assert result is not None
    assert result.value == "2026-04-29"
    assert result.conflict is False
    assert result.candidate_values == [
        {
            "value": "2026-04-29",
            "evidence": [
                {
                    "snippet": "A",
                    "page_numbers": [],
                    "doc_refs": [],
                    "images": [],
                    "matched_queries": [],
                }
            ],
        },
        {"value": "29.04.2026", "evidence": []},
    ]


def test_select_scalar_field_result_marks_conflict_for_supported_alternates():
    result = _select_scalar_field_result(
        [
            ("Project A", WorkerDocumentEvidence(snippet="A1"), None),
            ("Project A", WorkerDocumentEvidence(snippet="A2"), None),
            ("Project B", WorkerDocumentEvidence(snippet="B1"), None),
            ("Project B", WorkerDocumentEvidence(snippet="B2"), None),
        ],
        dtype="str",
        required=False,
    )

    assert result is not None
    assert result.conflict is True


def test_select_list_field_result_flattens_unique_values():
    evidence = WorkerDocumentEvidence(snippet="Items")

    result = _select_list_field_result(
        [
            (["A", "B"], evidence, 0.6),
            (["B", "C"], None, 0.9),
        ],
        required=False,
    )

    assert result is not None
    assert result.value == ["A", "B", "C"]
    assert result.candidate_values == [
        {
            "value": "A",
            "confidence": 0.6,
            "evidence": [
                {
                    "snippet": "Items",
                    "page_numbers": [],
                    "doc_refs": [],
                    "images": [],
                    "matched_queries": [],
                }
            ],
        },
        {
            "value": "B",
            "confidence": 0.9,
            "evidence": [
                {
                    "snippet": "Items",
                    "page_numbers": [],
                    "doc_refs": [],
                    "images": [],
                    "matched_queries": [],
                }
            ],
        },
        {"value": "C", "confidence": 0.9, "evidence": []},
    ]
    assert result.evidence == [evidence]
    assert result.confidence == 0.9
    assert result.conflict is False
