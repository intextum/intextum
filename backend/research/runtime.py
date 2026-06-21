"""Request-scoped runtime state for deep research generation."""

from dataclasses import dataclass, field

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from chat.context import ChatContextScope, build_context_scope
from chat.runtime import ChatRuntimeSettings
from models.user import User


@dataclass
class ResearchRuntime:
    """Dependencies and mutable request state for one research generation."""

    settings: ChatRuntimeSettings
    user: User
    db: AsyncSession
    embed_client: AsyncOpenAI
    context_file_paths: list[str]
    _context_scope: ChatContextScope | None = field(
        default=None, init=False, repr=False
    )

    @property
    def context_scope(self) -> ChatContextScope:
        """Return the resolved context scope for this research request."""
        if self._context_scope is None:
            self._context_scope = build_context_scope(self.context_file_paths)
        return self._context_scope
