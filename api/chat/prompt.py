"""Prompt helpers for the request-scoped chat runtime."""

import logging

from chat.runtime import ChatRuntime

logger = logging.getLogger(__name__)


def build_system_prompt(runtime: ChatRuntime) -> str:
    """Build the request-scoped system prompt for the chat model."""
    settings = runtime.settings
    base_prompt = settings.CHAT_SYSTEM_PROMPT.strip()
    tools_prompt = settings.CHAT_TOOL_PROMPT.strip()
    conversation_prompt = (
        "Conversation history in this thread is part of the available context. "
        "Previous assistant answers and deep research reports generated in this thread "
        "are valid context for follow-up questions. "
        'When the user asks about something already discussed, about "the report", '
        "or about prior research findings, answer from the conversation history directly. "
        "Do not claim information is missing from documents if it is already present in "
        "the conversation. Use tools when you need to inspect or verify underlying "
        "documents, gather fresh evidence, or answer something not already covered in "
        "the thread."
    )
    prompt = f"{base_prompt}\n\n{tools_prompt}\n\n{conversation_prompt}".strip()

    context_scope = runtime.context_scope
    if not context_scope.has_selection:
        return prompt

    logger.info(
        "Instructions context resolution: context_files=%d resolved_files=%d",
        len(context_scope.raw_paths),
        len(context_scope.constraints),
    )
    if not context_scope.has_constraints:
        logger.warning(
            "Context scope active but no valid context constraints. configured_folders=%s",
            sorted(context_scope.folder_names),
        )
        return (
            f"{prompt}\n\n"
            "Context files were specified, but none resolved to valid paths. "
            "Ask the user to add files to context before continuing."
        )

    scoped_paths = "\n".join(f"- {path}" for path, _, _ in context_scope.constraints)
    return (
        f"{prompt}\n\n"
        "The user has attached the following files to this conversation. "
        "When the user asks a question (e.g. 'summarize', 'explain', 'compare'), "
        "assume they are referring to these files. "
        "Use get_document to retrieve their full text, or "
        "search_documents to find specific passages. "
        "Restrict all tool calls to these files:\n"
        f"{scoped_paths}"
    )
