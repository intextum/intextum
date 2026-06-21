"""Request-scoped runtime state for chat generation."""

from dataclasses import dataclass, field

from models.ai_settings import EffectiveAiSettings
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from chat.collector import ChatSourceCollector
from chat.context import ChatContextScope, build_context_scope
from models.user import User
from services.ai_limits import (
    DEFAULT_AI_BACKPRESSURE_WAIT_SECONDS,
    DEFAULT_AI_CLIENT_MAX_RETRIES,
    DEFAULT_CHAT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_CHAT_TIMEOUT_SECONDS,
    DEFAULT_EMBEDDING_MAX_CONCURRENT_REQUESTS,
    DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
)


@dataclass(frozen=True)
class ChatRuntimeSettings:
    """Subset of backend settings needed by one chat generation run."""

    CHAT_API_BASE: str
    CHAT_API_KEY: str
    CHAT_MODEL: str
    CHAT_SYSTEM_PROMPT: str
    CHAT_TOOL_PROMPT: str
    CHAT_SEARCH_LIMIT: int
    CHAT_DOCUMENT_MAX_CHARS: int
    EMBEDDING_MODEL: str
    EMBEDDING_TIMEOUT_SECONDS: float = DEFAULT_EMBEDDING_TIMEOUT_SECONDS
    EMBEDDING_MAX_CONCURRENT_REQUESTS: int = DEFAULT_EMBEDDING_MAX_CONCURRENT_REQUESTS
    CHAT_TIMEOUT_SECONDS: float = DEFAULT_CHAT_TIMEOUT_SECONDS
    CHAT_MAX_CONCURRENT_REQUESTS: int = DEFAULT_CHAT_MAX_CONCURRENT_REQUESTS
    AI_BACKPRESSURE_WAIT_SECONDS: float = DEFAULT_AI_BACKPRESSURE_WAIT_SECONDS
    AI_CLIENT_MAX_RETRIES: int = DEFAULT_AI_CLIENT_MAX_RETRIES

    @classmethod
    def from_base_and_ai_settings(
        cls,
        *,
        base_settings,
        ai_settings: EffectiveAiSettings | None = None,
    ) -> "ChatRuntimeSettings":
        """Build request-scoped chat settings from deploy config plus overrides."""
        effective_ai = ai_settings or EffectiveAiSettings.model_validate(
            {
                "chat_model": base_settings.CHAT_MODEL,
                "chat_system_prompt": base_settings.CHAT_SYSTEM_PROMPT,
                "chat_tool_prompt": base_settings.CHAT_TOOL_PROMPT,
                "chat_search_limit": base_settings.CHAT_SEARCH_LIMIT,
                "chat_document_max_chars": base_settings.CHAT_DOCUMENT_MAX_CHARS,
                "picture_description_model": base_settings.PICTURE_DESCRIPTION_MODEL,
                "picture_description_prompt": base_settings.PICTURE_DESCRIPTION_PROMPT,
            }
        )
        return cls(
            CHAT_API_BASE=base_settings.CHAT_API_BASE,
            CHAT_API_KEY=base_settings.CHAT_API_KEY,
            CHAT_MODEL=effective_ai.chat_model,
            CHAT_SYSTEM_PROMPT=effective_ai.chat_system_prompt,
            CHAT_TOOL_PROMPT=effective_ai.chat_tool_prompt,
            CHAT_SEARCH_LIMIT=effective_ai.chat_search_limit,
            CHAT_DOCUMENT_MAX_CHARS=effective_ai.chat_document_max_chars,
            EMBEDDING_MODEL=base_settings.EMBEDDING_MODEL,
            EMBEDDING_TIMEOUT_SECONDS=getattr(
                base_settings,
                "EMBEDDING_TIMEOUT_SECONDS",
                DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
            ),
            EMBEDDING_MAX_CONCURRENT_REQUESTS=getattr(
                base_settings,
                "EMBEDDING_MAX_CONCURRENT_REQUESTS",
                DEFAULT_EMBEDDING_MAX_CONCURRENT_REQUESTS,
            ),
            CHAT_TIMEOUT_SECONDS=getattr(
                base_settings,
                "CHAT_TIMEOUT_SECONDS",
                DEFAULT_CHAT_TIMEOUT_SECONDS,
            ),
            CHAT_MAX_CONCURRENT_REQUESTS=getattr(
                base_settings,
                "CHAT_MAX_CONCURRENT_REQUESTS",
                DEFAULT_CHAT_MAX_CONCURRENT_REQUESTS,
            ),
            AI_BACKPRESSURE_WAIT_SECONDS=getattr(
                base_settings,
                "AI_BACKPRESSURE_WAIT_SECONDS",
                DEFAULT_AI_BACKPRESSURE_WAIT_SECONDS,
            ),
            AI_CLIENT_MAX_RETRIES=getattr(
                base_settings,
                "AI_CLIENT_MAX_RETRIES",
                DEFAULT_AI_CLIENT_MAX_RETRIES,
            ),
        )


@dataclass
class ChatRuntime:
    """Dependencies and mutable request state for one chat generation."""

    settings: ChatRuntimeSettings
    user: User
    db: AsyncSession
    embed_client: AsyncOpenAI
    context_file_paths: list[str]
    source_collector: ChatSourceCollector = field(default_factory=ChatSourceCollector)
    _context_scope: ChatContextScope | None = field(
        default=None, init=False, repr=False
    )

    @property
    def context_scope(self) -> ChatContextScope:
        """Return the resolved context scope for this request."""
        if self._context_scope is None:
            self._context_scope = build_context_scope(self.context_file_paths)
        return self._context_scope
