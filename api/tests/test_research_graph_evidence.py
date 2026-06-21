"""Focused tests for research graph evidence helpers."""

from types import SimpleNamespace

from research.graph.evidence import (
    _rank_section_candidates,
    _reviewed_evidence_section_candidates,
    _section_candidate_score,
)
from research.graph.structured import _scoring_terms


def test_section_candidate_score_uses_phrase_and_vector_signals():
    """Section candidate scoring should reward better vector scores and direct phrase matches."""
    prompt = "Assess retrofit priorities for the district heating plan."
    heading = "Recommendations"
    question = "Which retrofit priorities should happen next?"
    prompt_terms = _scoring_terms(prompt)
    heading_terms = _scoring_terms(heading)
    question_terms = _scoring_terms(question)
    query_terms = _scoring_terms(question)

    weaker = SimpleNamespace(
        text="Retrofitting controls should happen next in the heating plan.",
        doc_refs=[],
        score=0.61,
    )
    stronger = SimpleNamespace(
        text="Recommendations: retrofitting controls should happen next in the district heating plan.",
        doc_refs=[],
        score=0.93,
    )

    weak_score = _section_candidate_score(
        chunk=weaker,
        file_path="docs/controls.pdf",
        heading_text=heading,
        question_text=question,
        prompt_terms=prompt_terms,
        heading_terms=heading_terms,
        question_terms=question_terms,
        query_terms=query_terms,
        query_index=0,
        rank_index=0,
    )
    strong_score = _section_candidate_score(
        chunk=stronger,
        file_path="docs/high-priority-controls.pdf",
        heading_text=heading,
        question_text=question,
        prompt_terms=prompt_terms,
        heading_terms=heading_terms,
        question_terms=question_terms,
        query_terms=query_terms,
        query_index=0,
        rank_index=1,
    )

    assert strong_score > weak_score


def test_rank_section_candidates_caps_same_file_and_rewards_query_coverage():
    """Candidate ranking should cap same-file dominance and prefer wider query coverage."""
    ranked = _rank_section_candidates(
        candidates={
            ("docs/master.pdf", "a"): {
                "file_path": "docs/master.pdf",
                "score": 2.4,
                "first_query_index": 0,
                "first_rank_index": 0,
                "query_indices": {0, 1},
            },
            ("docs/master.pdf", "b"): {
                "file_path": "docs/master.pdf",
                "score": 2.2,
                "first_query_index": 0,
                "first_rank_index": 1,
                "query_indices": {0},
            },
            ("docs/master.pdf", "c"): {
                "file_path": "docs/master.pdf",
                "score": 2.1,
                "first_query_index": 1,
                "first_rank_index": 0,
                "query_indices": {1},
            },
            ("docs/roadmap.pdf", "d"): {
                "file_path": "docs/roadmap.pdf",
                "score": 2.0,
                "first_query_index": 0,
                "first_rank_index": 2,
                "query_indices": {0, 1},
            },
        }
    )

    assert [item["file_path"] for item in ranked] == [
        "docs/master.pdf",
        "docs/roadmap.pdf",
        "docs/master.pdf",
    ]


def test_reviewed_evidence_section_candidates_emit_reviewed_enrichment_payloads():
    """Reviewed evidence candidates should surface reviewed enrichment snippets as sources."""
    prompt = "Review the invoice and summarize the payment details."
    heading = "Payment Details"
    question = "Which invoice amounts and identifiers matter most?"

    candidates = _reviewed_evidence_section_candidates(
        structured_facts=[
            {
                "api_path": "documents/invoice.pdf",
                "document_class": "Invoice",
                "document_class_review_status": "corrected",
                "extraction_review_status": "accepted",
                "extraction_data": {
                    "invoice_number": "RE-2026-42",
                    "gross_amount": 119.0,
                },
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
        prompt=prompt,
        heading=heading,
        question=question,
        prompt_terms=_scoring_terms(prompt),
        heading_terms=_scoring_terms(heading),
        question_terms=_scoring_terms(question),
    )

    assert len(candidates) == 1
    assert candidates[0]["file_path"] == "documents/invoice.pdf"
    assert (
        candidates[0]["title"] == "Reviewed enrichment evidence: Field invoice_number"
    )
    assert candidates[0]["kind"] == "reviewed_enrichment"
    assert candidates[0]["text"] == "Rechnungsnummer RE-2026-42"
    assert candidates[0]["page_numbers"] == [1]
    assert candidates[0]["doc_refs"] == ["#/texts/4"]
    assert candidates[0]["images"] == []
    assert candidates[0]["first_query_index"] == 0
    assert candidates[0]["first_rank_index"] == 0
    assert candidates[0]["query_indices"] == {0}
    assert candidates[0]["score"] > 0
