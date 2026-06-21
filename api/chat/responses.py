"""Helpers for finalizing assistant responses before persistence."""

from langchain_core.messages import AIMessage

from chat.collector import ChatSourceCollector


def finalize_assistant_response(
    response: AIMessage,
    *,
    source_collector: ChatSourceCollector,
    created_at: str,
) -> AIMessage:
    """Attach persisted metadata to one model response when it is user-visible."""
    if getattr(response, "tool_calls", None):
        return response

    additional_kwargs = dict(getattr(response, "additional_kwargs", {}) or {})
    additional_kwargs["created_at"] = created_at
    if source_collector.has_sources():
        additional_kwargs["sources"] = source_collector.persisted_payloads()

    return response.model_copy(update={"additional_kwargs": additional_kwargs})
