"""LangGraph construction for the chat workflow."""

from typing import Any

from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from chat.checkpointer import get_chat_checkpointer
from chat.collector import ChatSourceCollector
from chat.enrichment import build_context_file_enrichment_context
from .report_context import build_latest_research_report_context
from chat.prompt import build_system_prompt
from chat.responses import finalize_assistant_response
from chat.runtime import ChatRuntime, ChatRuntimeSettings
from chat.state import ChatGraphState
from chat.time import iso_now
from chat.tools import build_chat_tools
from clients import get_async_embedding_client
from config import get_settings
from models.ai_settings import EffectiveAiSettings
from models.user import User
from services.ai_limits import (
    DEFAULT_CHAT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_CHAT_TIMEOUT_SECONDS,
    ai_client_max_retries,
    ai_timeout_seconds,
    run_ai_call,
)


def _latest_research_report_context(
    messages: list[AnyMessage],
    *,
    source_collector: ChatSourceCollector,
) -> str | None:
    return build_latest_research_report_context(
        messages,
        source_collector=source_collector,
    )


def _messages_for_model(
    *,
    system_parts: list[str],
    conversation_messages: list[AnyMessage],
) -> list[AnyMessage]:
    """Return a provider-compatible transcript with exactly one leading system message."""
    combined_system_parts = [part.strip() for part in system_parts if part.strip()]
    non_system_messages: list[AnyMessage] = []
    for message in conversation_messages:
        if (
            isinstance(message, SystemMessage)
            or getattr(message, "type", None) == "system"
        ):
            content = str(message.content).strip()
            if content:
                combined_system_parts.append(content)
            continue
        non_system_messages.append(message)

    if not combined_system_parts:
        return non_system_messages

    return [
        SystemMessage(content="\n\n".join(combined_system_parts)),
        *non_system_messages,
    ]


def build_chat_graph(runtime: ChatRuntime, *, checkpointer):
    """Build a request-scoped LangGraph with tool-calling support."""
    tools = build_chat_tools(runtime)
    model = ChatOpenAI(
        base_url=runtime.settings.CHAT_API_BASE,
        api_key=runtime.settings.CHAT_API_KEY,
        model=runtime.settings.CHAT_MODEL,
        streaming=True,
        timeout=ai_timeout_seconds(
            runtime.settings,
            "CHAT_TIMEOUT_SECONDS",
            DEFAULT_CHAT_TIMEOUT_SECONDS,
        ),
        max_retries=ai_client_max_retries(runtime.settings),
    ).bind_tools(tools)

    async def call_model(state: ChatGraphState):
        conversation_messages = list(state["messages"])
        system_parts = [build_system_prompt(runtime)]
        context_file_enrichment = await build_context_file_enrichment_context(
            db=runtime.db,
            user=runtime.user,
            context_scope=runtime.context_scope,
            source_collector=runtime.source_collector,
        )
        if context_file_enrichment:
            system_parts.append(context_file_enrichment)
        research_report_context = _latest_research_report_context(
            conversation_messages,
            source_collector=runtime.source_collector,
        )
        if research_report_context:
            system_parts.append(research_report_context)
        response = await run_ai_call(
            lambda: model.ainvoke(
                _messages_for_model(
                    system_parts=system_parts,
                    conversation_messages=conversation_messages,
                )
            ),
            settings=runtime.settings,
            name="chat",
            timeout_attr="CHAT_TIMEOUT_SECONDS",
            default_timeout_seconds=DEFAULT_CHAT_TIMEOUT_SECONDS,
            concurrency_attr="CHAT_MAX_CONCURRENT_REQUESTS",
            default_concurrency=DEFAULT_CHAT_MAX_CONCURRENT_REQUESTS,
            timeout_detail="Chat model request timed out",
            busy_detail="Chat model is busy",
        )
        response = finalize_assistant_response(
            response,
            source_collector=runtime.source_collector,
            created_at=iso_now(),
        )
        return {"messages": [response]}

    builder = StateGraph(ChatGraphState)
    builder.add_node("chatbot", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges("chatbot", tools_condition)
    builder.add_edge("tools", "chatbot")
    return builder.compile(checkpointer=checkpointer)


def build_request_scoped_chat_graph(
    *,
    db: AsyncSession,
    user: User,
    context_file_paths: list[str],
    ai_settings: EffectiveAiSettings | None = None,
    persist_checkpoints: bool = True,
) -> Any:
    """Build a compiled LangGraph with request-scoped runtime dependencies."""
    base_settings = get_settings()
    runtime = ChatRuntime(
        settings=ChatRuntimeSettings.from_base_and_ai_settings(
            base_settings=base_settings,
            ai_settings=ai_settings,
        ),
        user=user,
        db=db,
        embed_client=get_async_embedding_client(),
        context_file_paths=context_file_paths,
    )
    checkpointer = get_chat_checkpointer() if persist_checkpoints else None
    return build_chat_graph(runtime, checkpointer=checkpointer)
