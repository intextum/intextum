"""Focused tests for deep research graph quality behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from chat.retrieval import RetrievedChunk
from research import graph
from research.graph.structured import _relevant_structured_facts


def _runtime():
    return SimpleNamespace(
        settings=SimpleNamespace(
            CHAT_SEARCH_LIMIT=4,
            CHAT_API_BASE="http://example.invalid",
            CHAT_API_KEY="test-key",
            CHAT_MODEL="test-model",
        ),
        db=AsyncMock(),
        user=SimpleNamespace(username="tester", sub="sub-tester"),
        context_scope=SimpleNamespace(
            folder_uuid_to_name={},
            file_ids=[],
            has_constraints=False,
        ),
    )


def _chunk(
    *,
    text: str,
    file_path: str,
    content_item_id: str,
    score: float | None = None,
    page_numbers: list[int] | None = None,
    doc_refs: list[str] | None = None,
    images: list[str] | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        score=score,
        file_path=file_path,
        content_item_id=content_item_id,
        page_numbers=[] if page_numbers is None else page_numbers,
        doc_refs=[] if doc_refs is None else doc_refs,
        images=[] if images is None else images,
    )


@pytest.mark.asyncio
async def test_collect_section_evidence_groups_sources_by_section():
    runtime = _runtime()
    state = {
        "prompt": "Assess the sustainability program.",
        "outline": ["Summary", "Recommendations"],
        "questions": [
            "What does the current program achieve?",
            "Which actions should be recommended next?",
        ],
    }
    shared = _chunk(
        text="Annual emissions fell by 12 percent after the retrofit.",
        file_path="docs/program.pdf",
        content_item_id="file-shared",
        page_numbers=[3],
    )
    summary_only = _chunk(
        text="The baseline analysis highlights uneven impact across sites.",
        file_path="docs/analysis.pdf",
        content_item_id="file-summary",
        page_numbers=[5],
    )
    recommendations_only = _chunk(
        text="The roadmap prioritizes heating upgrades and monitoring.",
        file_path="docs/roadmap.pdf",
        content_item_id="file-rec",
        page_numbers=[8],
    )

    async def fake_search(_runtime_arg, query: str, *, limit: int):
        assert limit == 4
        if "Summary" in query or "current program" in query:
            return [shared, summary_only]
        if "Recommendations" in query or "recommended next" in query:
            return [shared, recommendations_only]
        return []

    with patch(
        "research.graph.core._semantic_search", new=AsyncMock(side_effect=fake_search)
    ):
        result = await graph._collect_section_evidence(runtime, state)

    assert [item["citation_index"] for item in result["evidence"]] == [1, 2, 3]
    assert [item["file_path"] for item in result["sources"]] == [
        "docs/program.pdf",
        "docs/analysis.pdf",
        "docs/roadmap.pdf",
    ]
    assert result["section_evidence"] == [
        {
            "heading": "Summary",
            "question": "What does the current program achieve?",
            "evidence": [result["evidence"][0], result["evidence"][1]],
            "citation_indices": [1, 2],
        },
        {
            "heading": "Recommendations",
            "question": "Which actions should be recommended next?",
            "evidence": [result["evidence"][0], result["evidence"][2]],
            "citation_indices": [1, 3],
        },
    ]


@pytest.mark.asyncio
async def test_collect_section_evidence_adds_single_document_context_to_sections():
    runtime = _runtime()
    state = {
        "prompt": "Summarize all duties in the selected agreement.",
        "outline": ["Duties", "Risks"],
        "questions": [
            "Which duties are described?",
            "Which risks are implied?",
        ],
        "single_document_context": {
            "file_path": "documents/agreement.pdf",
            "content_item_id": "content-agreement",
            "display_name": "agreement.pdf",
            "content_kind": "file",
            "page_numbers": [1, 2],
            "doc_refs": ["#/texts/1", "#/texts/8"],
            "images": ["/api/content/extracted-asset/content-agreement/page-1.png"],
            "text": "The agreement requires annual inspections and written reporting.",
        },
    }

    with patch(
        "research.graph.core._semantic_search",
        new=AsyncMock(return_value=[]),
    ):
        result = await graph._collect_section_evidence(runtime, state)

    assert result["evidence"] == [
        {
            "citation_index": 1,
            "file_path": "documents/agreement.pdf",
            "page_numbers": [1, 2],
            "doc_refs": ["#/texts/1", "#/texts/8"],
            "images": ["/api/content/extracted-asset/content-agreement/page-1.png"],
            "text": "The agreement requires annual inspections and written reporting.",
            "content_item_id": "content-agreement",
            "display_name": "agreement.pdf",
            "content_kind": "file",
        }
    ]
    assert result["sources"] == [
        {
            "file_path": "documents/agreement.pdf",
            "content_item_id": "content-agreement",
            "display_name": "agreement.pdf",
            "title": "Selected document: agreement.pdf",
            "content_kind": "file",
            "page_numbers": [1, 2],
            "doc_refs": ["#/texts/1", "#/texts/8"],
            "images": ["/api/content/extracted-asset/content-agreement/page-1.png"],
            "citation_index": 1,
            "quote": "The agreement requires annual inspections and written reporting.",
        }
    ]
    assert result["section_evidence"] == [
        {
            "heading": "Duties",
            "question": "Which duties are described?",
            "evidence": result["evidence"],
            "citation_indices": [1],
        },
        {
            "heading": "Risks",
            "question": "Which risks are implied?",
            "evidence": result["evidence"],
            "citation_indices": [1],
        },
    ]


@pytest.mark.asyncio
async def test_collect_structured_facts_uses_effective_context_file_enrichment():
    runtime = _runtime()
    expected = [
        {
            "api_path": "documents/invoice.pdf",
            "document_class": "Invoice",
            "document_class_source": "user_override",
            "extraction_data": {"invoice_number": "RE-2026-42"},
            "extraction_source": "document_processing",
        }
    ]

    with patch(
        "research.graph.core.load_effective_context_file_enrichment",
        new=AsyncMock(return_value=expected),
    ) as load_enrichment:
        result = await graph._collect_structured_facts(runtime, {"prompt": "Summarize"})

    assert result == {"structured_facts": expected}
    load_enrichment.assert_awaited_once_with(
        db=runtime.db,
        user=runtime.user,
        context_scope=runtime.context_scope,
    )


@pytest.mark.asyncio
async def test_collect_section_evidence_includes_reviewed_structured_evidence_sources():
    runtime = _runtime()
    state = {
        "prompt": "Review the invoice and summarize the payment details.",
        "outline": ["Payment Details"],
        "questions": ["Which invoice amounts and identifiers matter most?"],
        "structured_facts": [
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
    }

    with patch(
        "research.graph.core._semantic_search",
        new=AsyncMock(return_value=[]),
    ):
        result = await graph._collect_section_evidence(runtime, state)

    assert result["evidence"] == [
        {
            "citation_index": 1,
            "file_path": "documents/invoice.pdf",
            "page_numbers": [1],
            "doc_refs": ["#/texts/4"],
            "images": [],
            "text": "Rechnungsnummer RE-2026-42",
        }
    ]
    assert result["sources"] == [
        {
            "file_path": "documents/invoice.pdf",
            "display_name": "invoice.pdf",
            "title": "Reviewed enrichment evidence: Field invoice_number",
            "source_kind": "reviewed_enrichment",
            "page_numbers": [1],
            "doc_refs": ["#/texts/4"],
            "images": [],
            "citation_index": 1,
            "quote": "Rechnungsnummer RE-2026-42",
        }
    ]
    assert result["section_evidence"] == [
        {
            "heading": "Payment Details",
            "question": "Which invoice amounts and identifiers matter most?",
            "evidence": result["evidence"],
            "citation_indices": [1],
        }
    ]


@pytest.mark.asyncio
async def test_collect_section_evidence_reranks_late_more_relevant_chunks():
    runtime = _runtime()
    state = {
        "prompt": "Assess heating upgrades for the campus estate.",
        "outline": ["Heating Upgrades"],
        "questions": ["Which heating upgrades reduce energy use most effectively?"],
    }
    weak_match = _chunk(
        text="The campus estate includes several administrative buildings.",
        file_path="docs/estate-overview.pdf",
        content_item_id="file-overview",
    )
    strong_match = _chunk(
        text=(
            "Heating upgrades with heat pumps and insulation delivered the "
            "largest reduction in campus energy use."
        ),
        file_path="docs/heating-upgrades.pdf",
        content_item_id="file-heating",
    )

    with patch(
        "research.graph.core._semantic_search",
        new=AsyncMock(return_value=[weak_match, strong_match]),
    ):
        result = await graph._collect_section_evidence(runtime, state)

    assert [
        item["file_path"] for item in result["section_evidence"][0]["evidence"]
    ] == [
        "docs/heating-upgrades.pdf",
        "docs/estate-overview.pdf",
    ]
    assert [item["citation_index"] for item in result["evidence"]] == [1, 2]


@pytest.mark.asyncio
async def test_collect_section_evidence_uses_vector_score_as_ranking_signal():
    runtime = _runtime()
    state = {
        "prompt": "Assess retrofit priorities for the district heating plan.",
        "outline": ["Recommendations"],
        "questions": ["Which retrofit priorities should happen next?"],
    }
    lower_score = _chunk(
        text="Retrofitting controls should happen next in the district heating plan.",
        score=0.61,
        file_path="docs/controls.pdf",
        content_item_id="file-controls",
    )
    higher_score = _chunk(
        text="Retrofitting controls should happen next in the district heating plan.",
        score=0.93,
        file_path="docs/high-priority-controls.pdf",
        content_item_id="file-controls-best",
    )

    with patch(
        "research.graph.core._semantic_search",
        new=AsyncMock(return_value=[lower_score, higher_score]),
    ):
        result = await graph._collect_section_evidence(runtime, state)

    assert [
        item["file_path"] for item in result["section_evidence"][0]["evidence"]
    ] == [
        "docs/high-priority-controls.pdf",
        "docs/controls.pdf",
    ]
    assert [item["citation_index"] for item in result["evidence"]] == [1, 2]


@pytest.mark.asyncio
async def test_collect_section_evidence_caps_same_file_dominance():
    runtime = _runtime()
    state = {
        "prompt": "Assess retrofit priorities for the district heating plan.",
        "outline": ["Recommendations"],
        "questions": ["Which retrofit priorities should happen next?"],
    }
    same_content_chunks = [
        _chunk(
            text=f"District retrofit recommendation {index} prioritizes insulation and controls.",
            file_path="docs/master-plan.pdf",
            content_item_id="file-master",
            page_numbers=[index],
        )
        for index in range(1, 5)
    ]
    other_file_chunk = _chunk(
        text="A separate roadmap recommends phasing boiler replacement after controls upgrades.",
        file_path="docs/roadmap.pdf",
        content_item_id="file-roadmap",
        page_numbers=[7],
    )

    with patch(
        "research.graph.core._semantic_search",
        new=AsyncMock(return_value=[*same_content_chunks, other_file_chunk]),
    ):
        result = await graph._collect_section_evidence(runtime, state)

    selected_paths = [
        item["file_path"] for item in result["section_evidence"][0]["evidence"]
    ]
    assert selected_paths.count("docs/master-plan.pdf") == 2
    assert "docs/roadmap.pdf" in selected_paths


@pytest.mark.asyncio
async def test_draft_sections_uses_only_section_specific_evidence():
    runtime = _runtime()
    state = {
        "prompt": "Assess the sustainability program.",
        "title": "Program Review",
        "section_evidence": [
            {
                "heading": "Summary",
                "question": "What happened?",
                "evidence": [
                    {
                        "citation_index": 1,
                        "file_path": "docs/program.pdf",
                        "page_numbers": [3],
                        "doc_refs": [],
                        "images": [],
                        "text": "Annual emissions fell by 12 percent after the retrofit.",
                    }
                ],
                "citation_indices": [1],
            },
            {
                "heading": "Recommendations",
                "question": "What next?",
                "evidence": [],
                "citation_indices": [],
            },
        ],
    }

    with patch(
        "research.graph.core._invoke_json_schema",
        new=AsyncMock(
            return_value=graph._ResearchSectionDraft(
                body="The retrofit reduced emissions measurably. [1]"
            )
        ),
    ) as invoke_json:
        result = await graph._draft_sections(runtime, state)

    assert result["sections"] == [
        {
            "heading": "Summary",
            "body": "The retrofit reduced emissions measurably. [1]",
        },
        {
            "heading": "Recommendations",
            "body": (
                "The available documents did not provide enough section-specific evidence "
                "to support this part of the report."
            ),
        },
    ]
    invoke_json.assert_awaited_once()
    assert "Section heading:\nSummary" in invoke_json.await_args.kwargs["user_prompt"]
    assert (
        "[1] docs/program.pdf (pages 3)" in invoke_json.await_args.kwargs["user_prompt"]
    )


def test_section_prompt_includes_relevant_structured_facts():
    prompt = graph._section_prompt(
        {
            "prompt": "Review the invoice and summarize the payment details.",
            "title": "Invoice Review",
            "structured_facts": [
                {
                    "api_path": "documents/invoice.pdf",
                    "document_class": "Invoice",
                    "document_class_source": "user_override",
                    "document_class_review_status": "corrected",
                    "extraction_data": {
                        "invoice_number": "RE-2026-42",
                        "gross_amount": 119.0,
                        "vat_amount": 19.0,
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
                },
                {
                    "api_path": "documents/permit.pdf",
                    "document_class": "Permit",
                    "document_class_source": "document_processing",
                    "extraction_data": {"authority": "County Office"},
                    "extraction_source": "document_processing",
                },
            ],
        },
        {
            "heading": "Payment Details",
            "question": "Which invoice amounts and identifiers matter most?",
            "evidence": [],
        },
    )

    assert "Structured file facts:" in prompt
    assert "documents/invoice.pdf" in prompt
    assert (
        "Document class: Invoice (user correction, human-reviewed corrected)" in prompt
    )
    assert "Extracted fields (document processing, human-reviewed accepted):" in prompt
    assert "gross_amount: 119.0" in prompt
    assert "vat_amount: 19.0" in prompt
    assert "Reviewed enrichment evidence snippets:" in prompt
    assert (
        "Field invoice_number (pages 1; refs #/texts/4): Rechnungsnummer RE-2026-42"
        in prompt
    )
    assert "documents/permit.pdf" not in prompt
    assert "Prefer human-reviewed accepted or corrected facts" in prompt
    assert "Do not cite the structured file facts directly" in prompt


def test_planner_prompt_includes_structured_facts():
    prompt = graph._planner_prompt(
        {
            "prompt": "Assess the sustainability program.",
            "context_file_paths": ["documents/program.pdf"],
            "structured_facts": [
                {
                    "api_path": "documents/program.pdf",
                    "document_class": "Program Report",
                    "document_class_source": "document_processing",
                    "document_class_review_status": "accepted",
                    "extraction_data": {
                        "program_name": "Sustainability Program",
                        "review_year": 2026,
                    },
                    "extraction_source": "document_processing",
                    "reviewed_evidence": [
                        {
                            "label": "Field program_name",
                            "snippet": "Sustainability Program annual review 2026",
                            "page_numbers": [2],
                            "doc_refs": ["#/texts/8"],
                        }
                    ],
                }
            ],
        }
    )

    assert "Structured document facts:" in prompt
    assert "documents/program.pdf" in prompt
    assert (
        "Document class: Program Report (document processing, human-reviewed accepted)"
        in prompt
    )
    assert "program_name: Sustainability Program" in prompt
    assert (
        "Field program_name (pages 2; refs #/texts/8): Sustainability Program annual review 2026"
        in prompt
    )
    assert "reviewed enrichment evidence snippets are present" in prompt


def test_relevant_structured_facts_prefers_reviewed_matches():
    selected = _relevant_structured_facts(
        structured_facts=[
            {
                "api_path": "documents/unreviewed-invoice.pdf",
                "document_class": "Invoice",
                "document_class_source": "document_processing",
                "extraction_data": {
                    "invoice_number": "RE-2026-1",
                    "gross_amount": 100.0,
                },
                "extraction_source": "document_processing",
            },
            {
                "api_path": "documents/reviewed-invoice.pdf",
                "document_class": "Invoice",
                "document_class_source": "document_processing",
                "document_class_review_status": "accepted",
                "extraction_data": {
                    "invoice_number": "RE-2026-2",
                    "gross_amount": 120.0,
                },
                "extraction_source": "document_processing",
                "extraction_review_status": "accepted",
            },
        ],
        prompt="Review the invoice and summarize payment details.",
        heading="Payment Details",
        question="Which invoice amounts and identifiers matter most?",
    )

    assert selected[0]["api_path"] == "documents/reviewed-invoice.pdf"


@pytest.mark.asyncio
async def test_invoke_json_schema_accepts_plain_text_for_single_string_schema():
    runtime = _runtime()
    fake_model = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(
                content="```markdown\nRetention improved after the program [1].\n```"
            )
        )
    )

    with patch("research.graph.core._chat_model", return_value=fake_model):
        result = await graph._invoke_json_schema(
            runtime=runtime,
            schema=graph._ResearchSectionDraft,
            system_prompt="Return JSON.",
            user_prompt="Draft the section.",
        )

    assert result == graph._ResearchSectionDraft(
        body="Retention improved after the program [1]."
    )


def test_verification_issues_flag_missing_invalid_and_cross_section_citations():
    issues = graph._verification_issues(
        sections=[
            {
                "heading": "Summary",
                "body": "This section makes claims without citations.",
            },
            {
                "heading": "Recommendations",
                "body": "Act on the retrofit evidence [1] and [9].",
            },
        ],
        sources=[
            {"citation_index": 1, "file_path": "docs/program.pdf"},
            {"citation_index": 2, "file_path": "docs/analysis.pdf"},
            {"citation_index": 3, "file_path": "docs/roadmap.pdf"},
        ],
        section_evidence=[
            {"citation_indices": [1, 2]},
            {"citation_indices": [3]},
        ],
    )

    assert (
        "Summary: section evidence was retrieved but the draft cites none of it"
        in issues
    )
    assert "Recommendations: invalid citations 9" in issues
    assert "Recommendations: cites sources outside the section evidence 1" in issues


@pytest.mark.asyncio
async def test_build_research_graph_runs_section_grounded_flow():
    runtime = _runtime()
    shared = _chunk(
        text="Annual emissions fell by 12 percent after the retrofit.",
        file_path="docs/program.pdf",
        content_item_id="file-shared",
        page_numbers=[3],
        images=["chart.png"],
    )
    roadmap = _chunk(
        text="The roadmap prioritizes heating upgrades and monitoring.",
        file_path="docs/roadmap.pdf",
        content_item_id="file-roadmap",
        page_numbers=[8],
    )

    async def fake_search(_runtime_arg, query: str, *, limit: int):
        assert limit == 4
        if "Summary" in query:
            return [shared]
        if "Recommendations" in query:
            return [roadmap]
        return []

    prompts: list[str] = []

    async def fake_invoke(*, schema, user_prompt, **_kwargs):
        prompts.append(user_prompt)
        if schema is graph._ResearchPlan:
            return graph._ResearchPlan(
                title="Program Review",
                questions=["What changed?", "What should happen next?"],
                outline=["Summary", "Recommendations"],
            )
        if (
            schema is graph._ResearchSectionDraft
            and "Section heading:\nSummary" in user_prompt
        ):
            return graph._ResearchSectionDraft(
                body="The retrofit reduced emissions measurably. [1]"
            )
        if (
            schema is graph._ResearchSectionDraft
            and "Section heading:\nRecommendations" in user_prompt
        ):
            return graph._ResearchSectionDraft(
                body="Prioritize the roadmap actions next. [2]"
            )
        raise AssertionError(f"Unexpected invocation for schema={schema}")

    compiled = graph.build_research_graph(runtime)
    with (
        patch(
            "research.graph.core.load_effective_context_file_enrichment",
            new=AsyncMock(
                return_value=[
                    {
                        "api_path": "documents/program.pdf",
                        "document_class": "Program Report",
                        "document_class_source": "document_processing",
                        "extraction_data": {
                            "program_name": "Sustainability Program",
                            "review_year": 2026,
                        },
                        "extraction_source": "document_processing",
                    }
                ]
            ),
        ),
        patch(
            "research.graph.core._semantic_search",
            new=AsyncMock(side_effect=fake_search),
        ),
        patch(
            "research.graph.core._invoke_json_schema",
            new=AsyncMock(side_effect=fake_invoke),
        ),
    ):
        result = await compiled.ainvoke(
            {"prompt": "Assess the sustainability program.", "context_file_paths": []}
        )

    assert result["title"] == "Program Review"
    assert result["outline"] == ["Summary", "Recommendations"]
    assert [item["citation_indices"] for item in result["section_evidence"]] == [
        [1],
        [2],
    ]
    assert result["sections"] == [
        {
            "heading": "Summary",
            "body": "The retrofit reduced emissions measurably. [1]",
        },
        {
            "heading": "Recommendations",
            "body": "Prioritize the roadmap actions next. [2]",
        },
    ]
    assert result["verification_issues"] == []
    assert result["images"] == [
        {
            "url": "/api/content/extracted-asset/file-shared/chart.png",
            "title": "program.pdf",
            "citation_index": 1,
        }
    ]
    assert "## Summary" in result["content_markdown"]
    assert "## Sources" in result["content_markdown"]
    assert result["structured_facts"] == [
        {
            "api_path": "documents/program.pdf",
            "document_class": "Program Report",
            "document_class_source": "document_processing",
            "extraction_data": {
                "program_name": "Sustainability Program",
                "review_year": 2026,
            },
            "extraction_source": "document_processing",
        }
    ]
    assert any("Structured file facts:" in prompt for prompt in prompts)
    assert any("program_name: Sustainability Program" in prompt for prompt in prompts)
