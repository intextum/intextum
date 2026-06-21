"""LangGraph construction for the deep research workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langgraph.graph import END, START, StateGraph
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chat.runtime import ChatRuntimeSettings
from chat.sources import CollectedSource, build_source_payload
from clients import get_async_embedding_client
from config import get_settings
from models.ai_settings import EffectiveAiSettings
from models.content.items import ContentItemKind
from models.user import User
from research.graph.evidence import (
    _MAX_SECTION_SOURCES,
    _rank_section_candidates,
    _reviewed_evidence_section_candidates,
    _section_candidate_score,
)
from research.graph.llm import (
    _invoke_json_schema as _invoke_json_schema_impl,
)
from research.graph.output import (
    _compose_markdown,
    _select_images,
    _verification_issues,
)
from research.graph.prompting import (
    _fallback_title,
    _planner_prompt,
    _section_plans,
    _section_prompt,
    _section_query_candidates,
)
from research.graph.runtime import (
    _collect_structured_facts as _collect_structured_facts_impl,
    _load_single_context_document as _load_single_context_document_impl,
    _resolved_file_path as _resolved_file_path_impl,
    _semantic_search as _semantic_search_impl,
)
from research.runtime import ResearchRuntime
from research.state import ResearchGraphState
from research.graph.structured import (
    _scoring_terms,
)
from services.content.enrichment_context import load_effective_context_file_enrichment
from services.ai_limits import (
    DEFAULT_CHAT_TIMEOUT_SECONDS,
    ai_client_max_retries,
    ai_timeout_seconds,
)

_MAX_QUERIES = 6
_MAX_SOURCES = 12
_VECTOR_SCORE_WEIGHT = 2.0


class _ResearchPlan(BaseModel):
    title: str | None = None
    questions: list[str] = Field(default_factory=list)
    outline: list[str] = Field(default_factory=list)


class _ResearchSectionDraft(BaseModel):
    body: str


def _chat_model(runtime: ResearchRuntime) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=runtime.settings.CHAT_API_BASE,
        api_key=runtime.settings.CHAT_API_KEY,
        model=runtime.settings.CHAT_MODEL,
        streaming=False,
        temperature=0,
        timeout=ai_timeout_seconds(
            runtime.settings,
            "CHAT_TIMEOUT_SECONDS",
            DEFAULT_CHAT_TIMEOUT_SECONDS,
        ),
        max_retries=ai_client_max_retries(runtime.settings),
    )


async def _invoke_json_schema(
    *,
    runtime: ResearchRuntime,
    schema: type[BaseModel],
    system_prompt: str,
    user_prompt: str,
) -> BaseModel:
    return await _invoke_json_schema_impl(
        runtime=runtime,
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_builder=_chat_model,
    )


def _resolved_file_path(runtime: ResearchRuntime, chunk) -> str:
    return _resolved_file_path_impl(runtime, chunk)


async def _semantic_search(
    runtime: ResearchRuntime, query: str, *, limit: int
) -> list[Any]:
    return await _semantic_search_impl(runtime, query, limit=limit)


async def _load_single_context_document(
    runtime: ResearchRuntime,
) -> dict[str, Any] | None:
    return await _load_single_context_document_impl(runtime)


async def _collect_structured_facts(
    runtime: ResearchRuntime,
    state: ResearchGraphState,
) -> dict[str, Any]:
    result = await _collect_structured_facts_impl(
        runtime,
        state,
        loader=load_effective_context_file_enrichment,
    )
    single_document_context = await _load_single_context_document(runtime)
    if single_document_context is not None:
        result["single_document_context"] = single_document_context
    return result


def _content_kind_from_value(value: Any) -> ContentItemKind | None:
    if isinstance(value, ContentItemKind):
        return value
    if isinstance(value, str) and value in {item.value for item in ContentItemKind}:
        return ContentItemKind(value)
    return None


def _datetime_from_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _single_document_evidence(
    state: ResearchGraphState,
    *,
    citation_index: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    context = state.get("single_document_context")
    if not isinstance(context, dict):
        return None

    file_path = context.get("file_path")
    text = context.get("text")
    if not isinstance(file_path, str) or not file_path:
        return None
    if not isinstance(text, str) or not text.strip():
        return None

    evidence_item: dict[str, Any] = {
        "citation_index": citation_index,
        "file_path": file_path,
        "page_numbers": list(context.get("page_numbers", [])),
        "doc_refs": list(context.get("doc_refs", [])),
        "images": list(context.get("images", [])),
        "text": text,
    }
    if isinstance(context.get("content_item_id"), str) and context.get(
        "content_item_id"
    ):
        evidence_item["content_item_id"] = context["content_item_id"]
    if isinstance(context.get("display_name"), str) and context.get("display_name"):
        evidence_item["display_name"] = context["display_name"]
    if isinstance(context.get("content_kind"), str) and context.get("content_kind"):
        evidence_item["content_kind"] = context["content_kind"]
    if isinstance(context.get("email_from_address"), str) and context.get(
        "email_from_address"
    ):
        evidence_item["email_from_address"] = context["email_from_address"]
    if context.get("email_sent_at") is not None:
        email_sent_at = _datetime_from_value(context.get("email_sent_at"))
        if email_sent_at is not None:
            evidence_item["email_sent_at"] = email_sent_at.isoformat()
    if isinstance(context.get("parent_display_name"), str) and context.get(
        "parent_display_name"
    ):
        evidence_item["parent_display_name"] = context["parent_display_name"]

    source_payload = build_source_payload(
        CollectedSource(
            file_path=file_path,
            content_item_id=(
                context.get("content_item_id")
                if isinstance(context.get("content_item_id"), str)
                else None
            ),
            display_name=(
                context.get("display_name")
                if isinstance(context.get("display_name"), str)
                else None
            ),
            content_kind=_content_kind_from_value(context.get("content_kind")),
            email_from_address=(
                context.get("email_from_address")
                if isinstance(context.get("email_from_address"), str)
                else None
            ),
            email_sent_at=_datetime_from_value(context.get("email_sent_at")),
            parent_display_name=(
                context.get("parent_display_name")
                if isinstance(context.get("parent_display_name"), str)
                else None
            ),
            page_numbers=list(context.get("page_numbers", [])),
            doc_refs=list(context.get("doc_refs", [])),
            quote=text[:200],
            citation_index=citation_index,
            image_urls=list(context.get("images", [])),
            title=(
                f"Selected document: {context.get('display_name')}"
                if isinstance(context.get("display_name"), str)
                and context.get("display_name")
                else "Selected document"
            ),
        )
    )
    return evidence_item, source_payload


async def _collect_section_evidence(
    runtime: ResearchRuntime,
    state: ResearchGraphState,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    section_evidence: list[dict[str, Any]] = []
    evidence_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    next_citation_index = 1
    single_document_evidence = _single_document_evidence(
        state,
        citation_index=next_citation_index,
    )
    if single_document_evidence is not None:
        document_evidence_item, document_source_payload = single_document_evidence
        evidence.append(document_evidence_item)
        sources.append(document_source_payload)
        evidence_by_key[
            (
                document_evidence_item["file_path"],
                document_evidence_item["text"][:240],
            )
        ] = document_evidence_item
        next_citation_index += 1
    else:
        document_evidence_item = None

    for section_plan in _section_plans(state):
        prompt_terms = _scoring_terms(state["prompt"])
        heading_terms = _scoring_terms(section_plan["heading"])
        question_terms = _scoring_terms(section_plan["question"])
        section_candidates: dict[tuple[str, str], dict[str, Any]] = {}
        for query_index, query in enumerate(
            _section_query_candidates(
                prompt=state["prompt"],
                heading=section_plan["heading"],
                question=section_plan["question"],
            )
        ):
            chunks = await _semantic_search(
                runtime,
                query,
                limit=max(2, min(runtime.settings.CHAT_SEARCH_LIMIT, 4)),
            )
            query_terms = _scoring_terms(query)
            for rank_index, chunk in enumerate(chunks):
                file_path = _resolved_file_path(runtime, chunk)
                dedupe_key = (file_path, chunk.text[:240])
                candidate = section_candidates.get(dedupe_key)
                score = _section_candidate_score(
                    chunk=chunk,
                    file_path=file_path,
                    heading_text=section_plan["heading"],
                    question_text=section_plan["question"],
                    prompt_terms=prompt_terms,
                    heading_terms=heading_terms,
                    question_terms=question_terms,
                    query_terms=query_terms,
                    query_index=query_index,
                    rank_index=rank_index,
                )
                if candidate is None:
                    section_candidates[dedupe_key] = {
                        "chunk": chunk,
                        "file_path": file_path,
                        "score": score,
                        "first_query_index": query_index,
                        "first_rank_index": rank_index,
                        "query_indices": {query_index},
                    }
                else:
                    candidate["score"] = max(candidate["score"], score)
                    candidate["query_indices"].add(query_index)

        for candidate in _reviewed_evidence_section_candidates(
            structured_facts=[
                item
                for item in state.get("structured_facts", [])
                if isinstance(item, dict)
            ],
            prompt=state["prompt"],
            heading=section_plan["heading"],
            question=section_plan["question"],
            prompt_terms=prompt_terms,
            heading_terms=heading_terms,
            question_terms=question_terms,
        ):
            dedupe_key = (candidate["file_path"], candidate["text"][:240])
            existing = section_candidates.get(dedupe_key)
            if existing is None:
                section_candidates[dedupe_key] = candidate
            else:
                existing["score"] = max(existing["score"], candidate["score"])
                existing["query_indices"].update(candidate["query_indices"])

        section_items: list[dict[str, Any]] = []
        if document_evidence_item is not None:
            section_items.append(document_evidence_item)
        for candidate in _rank_section_candidates(
            candidates=section_candidates,
        ):
            file_path = candidate["file_path"]
            chunk = candidate.get("chunk")
            evidence_text = chunk.text if chunk is not None else candidate["text"]
            dedupe_key = (file_path, evidence_text[:240])
            evidence_item = evidence_by_key.get(dedupe_key)
            if evidence_item is None:
                if len(evidence) >= _MAX_SOURCES:
                    continue
                if chunk is not None:
                    evidence_item = {
                        "citation_index": next_citation_index,
                        "file_path": file_path,
                        "page_numbers": list(chunk.page_numbers),
                        "doc_refs": list(chunk.doc_refs),
                        "images": chunk.image_urls(),
                        "text": chunk.text,
                    }
                    if chunk.content_item_id:
                        evidence_item["content_item_id"] = chunk.content_item_id
                    if chunk.display_name and chunk.display_name != "unknown":
                        evidence_item["display_name"] = chunk.display_name
                    if chunk.content_kind is not None:
                        evidence_item["content_kind"] = chunk.content_kind.value
                    if chunk.email_from_address:
                        evidence_item["email_from_address"] = chunk.email_from_address
                    if chunk.email_sent_at is not None:
                        evidence_item["email_sent_at"] = chunk.email_sent_at.isoformat()
                    if chunk.parent_display_name:
                        evidence_item["parent_display_name"] = chunk.parent_display_name
                    source_payload = build_source_payload(
                        CollectedSource(
                            file_path=file_path,
                            content_item_id=chunk.content_item_id or None,
                            display_name=chunk.display_name or None,
                            content_kind=chunk.content_kind,
                            email_from_address=chunk.email_from_address,
                            email_sent_at=chunk.email_sent_at,
                            parent_display_name=chunk.parent_display_name,
                            page_numbers=list(chunk.page_numbers),
                            doc_refs=list(chunk.doc_refs),
                            quote=chunk.text[:200],
                            citation_index=next_citation_index,
                            image_urls=chunk.image_urls(),
                        )
                    )
                else:
                    evidence_item = {
                        "citation_index": next_citation_index,
                        "file_path": file_path,
                        "page_numbers": list(candidate.get("page_numbers", [])),
                        "doc_refs": list(candidate.get("doc_refs", [])),
                        "images": list(candidate.get("images", [])),
                        "text": candidate["text"],
                    }
                    if isinstance(
                        candidate.get("content_item_id"), str
                    ) and candidate.get("content_item_id"):
                        evidence_item["content_item_id"] = candidate["content_item_id"]
                    if isinstance(candidate.get("display_name"), str) and candidate.get(
                        "display_name"
                    ):
                        evidence_item["display_name"] = candidate["display_name"]
                    if isinstance(candidate.get("content_kind"), str) and candidate.get(
                        "content_kind"
                    ):
                        evidence_item["content_kind"] = candidate["content_kind"]
                    if isinstance(
                        candidate.get("email_from_address"), str
                    ) and candidate.get("email_from_address"):
                        evidence_item["email_from_address"] = candidate[
                            "email_from_address"
                        ]
                    if isinstance(
                        candidate.get("email_sent_at"), str
                    ) and candidate.get("email_sent_at"):
                        evidence_item["email_sent_at"] = candidate["email_sent_at"]
                    if isinstance(
                        candidate.get("parent_display_name"), str
                    ) and candidate.get("parent_display_name"):
                        evidence_item["parent_display_name"] = candidate[
                            "parent_display_name"
                        ]
                    source_payload = build_source_payload(
                        CollectedSource(
                            file_path=file_path,
                            content_item_id=(
                                candidate.get("content_item_id")
                                if isinstance(candidate.get("content_item_id"), str)
                                else None
                            ),
                            display_name=(
                                candidate.get("display_name")
                                if isinstance(candidate.get("display_name"), str)
                                else None
                            ),
                            content_kind=(
                                ContentItemKind(candidate.get("content_kind"))
                                if isinstance(candidate.get("content_kind"), str)
                                and candidate.get("content_kind")
                                in {item.value for item in ContentItemKind}
                                else None
                            ),
                            email_from_address=(
                                candidate.get("email_from_address")
                                if isinstance(candidate.get("email_from_address"), str)
                                else None
                            ),
                            email_sent_at=(
                                datetime.fromisoformat(
                                    candidate.get("email_sent_at").replace(
                                        "Z", "+00:00"
                                    )
                                )
                                if isinstance(candidate.get("email_sent_at"), str)
                                and candidate.get("email_sent_at")
                                else None
                            ),
                            parent_display_name=(
                                candidate.get("parent_display_name")
                                if isinstance(candidate.get("parent_display_name"), str)
                                else None
                            ),
                            page_numbers=list(candidate.get("page_numbers", [])),
                            doc_refs=list(candidate.get("doc_refs", [])),
                            quote=candidate["text"][:200],
                            citation_index=next_citation_index,
                            image_urls=list(candidate.get("images", [])),
                            source_kind=(
                                candidate.get("kind")
                                if candidate.get("kind") == "reviewed_enrichment"
                                else None
                            ),
                            title=candidate.get("title")
                            if isinstance(candidate.get("title"), str)
                            else None,
                        )
                    )
                evidence_by_key[dedupe_key] = evidence_item
                evidence.append(evidence_item)
                sources.append(source_payload)
                next_citation_index += 1

            if evidence_item in section_items:
                continue
            section_items.append(evidence_item)
            if len(section_items) >= _MAX_SECTION_SOURCES:
                break

        section_evidence.append(
            {
                "heading": section_plan["heading"],
                "question": section_plan["question"],
                "evidence": section_items,
                "citation_indices": [
                    item["citation_index"]
                    for item in section_items
                    if isinstance(item.get("citation_index"), int)
                ],
            }
        )

    return {
        "evidence": evidence,
        "sources": sources,
        "section_evidence": section_evidence,
    }


async def _draft_sections(
    runtime: ResearchRuntime,
    state: ResearchGraphState,
) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    section_plans = [
        item for item in state.get("section_evidence", []) if isinstance(item, dict)
    ]
    if not section_plans:
        section_plans = _section_plans(state)

    for section_plan in section_plans:
        heading = (
            section_plan.get("heading")
            if isinstance(section_plan.get("heading"), str)
            else "Section"
        )
        evidence = [
            item for item in section_plan.get("evidence", []) if isinstance(item, dict)
        ]
        if evidence:
            draft = _ResearchSectionDraft.model_validate(
                await _invoke_json_schema(
                    runtime=runtime,
                    schema=_ResearchSectionDraft,
                    system_prompt=(
                        "You write section drafts for deep research reports and stay strictly grounded in the supplied evidence. "
                        "Return only valid JSON."
                    ),
                    user_prompt=_section_prompt(state, section_plan),
                )
            )
            body = draft.body.strip()
        else:
            body = (
                "The available documents did not provide enough section-specific evidence "
                "to support this part of the report."
            )
        if not body:
            body = (
                "The available documents did not provide enough section-specific evidence "
                "to support this part of the report."
            )
        sections.append({"heading": heading, "body": body})

    if not sections:
        sections = [
            {
                "heading": "Findings",
                "body": "The available documents did not provide enough grounded evidence to draft a fuller report.",
            }
        ]
    return {"sections": sections}


def build_research_graph(runtime: ResearchRuntime):
    """Build a request-scoped LangGraph for deep research generation."""

    async def collect_structured_facts(state: ResearchGraphState) -> dict[str, Any]:
        return await _collect_structured_facts(runtime, state)

    async def plan_research(state: ResearchGraphState) -> dict[str, Any]:
        plan = _ResearchPlan.model_validate(
            await _invoke_json_schema(
                runtime=runtime,
                schema=_ResearchPlan,
                system_prompt=(
                    "You are planning a deep research report. "
                    "Produce concise, document-grounded plans in JSON."
                ),
                user_prompt=_planner_prompt(state),
            )
        )
        questions = [item.strip() for item in plan.questions if item.strip()][
            :_MAX_QUERIES
        ]
        outline = [item.strip() for item in plan.outline if item.strip()]
        return {
            "title": plan.title or _fallback_title(state["prompt"]),
            "questions": questions or [state["prompt"]],
            "outline": outline or ["Executive Summary", "Findings", "Recommendations"],
        }

    async def retrieve_evidence(state: ResearchGraphState) -> dict[str, Any]:
        return await _collect_section_evidence(runtime, state)

    async def draft_report(state: ResearchGraphState) -> dict[str, Any]:
        return await _draft_sections(runtime, state)

    async def verify_report(state: ResearchGraphState) -> dict[str, Any]:
        sections = [
            item for item in state.get("sections", []) if isinstance(item, dict)
        ]
        sources = [item for item in state.get("sources", []) if isinstance(item, dict)]
        section_evidence = [
            item for item in state.get("section_evidence", []) if isinstance(item, dict)
        ]
        return {
            "images": _select_images(sections=sections, sources=sources),
            "verification_issues": _verification_issues(
                sections=sections,
                sources=sources,
                section_evidence=section_evidence,
            ),
            "content_markdown": _compose_markdown(
                title=state.get("title"),
                sections=sections,
                sources=sources,
            ),
        }

    builder = StateGraph(ResearchGraphState)
    builder.add_node("collect_structured_facts", collect_structured_facts)
    builder.add_node("plan_research", plan_research)
    builder.add_node("retrieve_evidence", retrieve_evidence)
    builder.add_node("draft_report", draft_report)
    builder.add_node("verify_report", verify_report)
    builder.add_edge(START, "collect_structured_facts")
    builder.add_edge("collect_structured_facts", "plan_research")
    builder.add_edge("plan_research", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "draft_report")
    builder.add_edge("draft_report", "verify_report")
    builder.add_edge("verify_report", END)
    return builder.compile()


def build_request_scoped_research_graph(
    *,
    db: AsyncSession,
    user: User,
    context_file_paths: list[str],
    ai_settings: EffectiveAiSettings | None = None,
) -> Any:
    """Build a compiled LangGraph for one deep research request."""
    base_settings = get_settings()
    runtime = ResearchRuntime(
        settings=ChatRuntimeSettings.from_base_and_ai_settings(
            base_settings=base_settings,
            ai_settings=ai_settings,
        ),
        user=user,
        db=db,
        embed_client=get_async_embedding_client(),
        context_file_paths=context_file_paths,
    )
    return build_research_graph(runtime)
