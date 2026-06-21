"""Conversation service backed by materialized conversation metadata."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage
from sqlalchemy.ext.asyncio import AsyncSession

from chat.submissions import (
    build_human_messages,
    build_transcript_messages,
    derive_title_from_text,
)
from chat.manager import ChatThreadManager
from chat.run.service import ChatRunService
from chat.snapshot import ChatThreadSnapshot
from chat.state import ChatThreadStatePatch, build_title_state_update
from chat.time import iso_now
from chat.transport import ChatStreamServiceRequest, normalize_context_file_paths
from chat.transcript import build_conversation_detail
from models.chat import ChatStreamMessage
from models.conversation import ConversationDetail, ConversationSummary
from models.user import User
from services.conversation_records import ConversationRecordService

MANUAL_THREAD_UPDATE_NODE = "chatbot"
# A regenerate rewind leaves the previous user message as the latest state.
# Marking the manual checkpoint as a tools update makes LangGraph resume at
# the chatbot node instead of the chatbot's post-model tool decision edge.
REGENERATION_REWIND_NODE = "tools"


@dataclass(frozen=True)
class ConversationRegenerationRequest:
    """Prepared request payload for rerunning a visible assistant response."""

    messages: list[ChatStreamMessage]
    context_file_paths: list[str]


class ConversationService:
    """Manages conversations from metadata rows plus optional LangGraph state."""

    def __init__(self, db: AsyncSession, user: User):
        self.thread_manager = ChatThreadManager(db=db, user=user, context_file_paths=[])
        self.record_service = ConversationRecordService(db)

    @staticmethod
    def _updated_at_as_utc(updated_at: str) -> datetime:
        parsed = datetime.fromisoformat(updated_at)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _db_timestamp_to_iso(value: datetime | None) -> str:
        if value is None:
            return iso_now()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _message_text(message: AnyMessage) -> str:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""

        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)

    @staticmethod
    def _message_additional_kwargs(message: AnyMessage) -> dict:
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        return additional_kwargs if isinstance(additional_kwargs, dict) else {}

    @classmethod
    def _visible_message_role(cls, message: AnyMessage) -> str | None:
        if isinstance(message, HumanMessage):
            return "user"
        if not isinstance(message, AIMessage):
            return None
        if getattr(message, "tool_calls", None):
            return None
        additional_kwargs = cls._message_additional_kwargs(message)
        has_sources = bool(additional_kwargs.get("sources"))
        has_metadata = isinstance(additional_kwargs.get("metadata"), dict)
        if (
            not cls._message_text(message).strip()
            and not has_sources
            and not has_metadata
        ):
            return None
        return "assistant"

    @staticmethod
    def _record_summary(
        record,
        *,
        active_run_status: str | None = None,
    ) -> ConversationSummary:
        return ConversationSummary(
            id=record.id,
            title=record.title,
            created_at=ConversationService._db_timestamp_to_iso(record.created_at),
            updated_at=ConversationService._db_timestamp_to_iso(record.updated_at),
            active_run_status=active_run_status,
        )

    @staticmethod
    def _record_detail(record) -> ConversationDetail:
        return ConversationDetail(
            id=record.id,
            title=record.title,
            created_at=ConversationService._db_timestamp_to_iso(record.created_at),
            updated_at=ConversationService._db_timestamp_to_iso(record.updated_at),
            messages=[],
        )

    async def ensure_conversation_for_submission(
        self,
        stream_request: ChatStreamServiceRequest,
        *,
        now: str | None = None,
    ) -> None:
        """Materialize a conversation row before streaming or queueing a run."""
        resolved_now = now or iso_now()
        submitted_messages = build_human_messages(
            stream_request.messages,
            context_file_paths=stream_request.context_file_paths,
        )
        if not submitted_messages:
            raise ValueError("messages must include at least one user message")

        derived_title = derive_title_from_text(submitted_messages[0].content)
        record = await self.record_service.get_conversation(
            stream_request.conversation_id
        )
        if record is not None:
            if record.user_sub != self.thread_manager.user_sub:
                self.thread_manager.raise_if_not_owned(
                    ChatThreadSnapshot(user_sub=record.user_sub)
                )
            await self.record_service.upsert_conversation(
                conversation_id=record.id,
                user_sub=record.user_sub,
                title=record.title or derived_title,
                created_at=record.created_at,
                updated_at=resolved_now,
            )
            return

        await self.record_service.upsert_conversation(
            conversation_id=stream_request.conversation_id,
            user_sub=self.thread_manager.user_sub,
            title=derived_title,
            created_at=resolved_now,
            updated_at=resolved_now,
        )

    async def _load_owned_snapshot(
        self, conversation_id: str
    ) -> ChatThreadSnapshot | None:
        return await self.thread_manager.load_owned_snapshot(conversation_id)

    async def persist_submitted_messages(
        self,
        stream_request: ChatStreamServiceRequest,
        *,
        now: str | None = None,
    ) -> None:
        """Persist submitted human messages into the conversation thread state."""
        resolved_now = now or iso_now()
        submitted_messages = build_human_messages(
            stream_request.messages,
            context_file_paths=stream_request.context_file_paths,
        )
        if not submitted_messages:
            raise ValueError("messages must include at least one user message")

        record = await self.record_service.get_owned_conversation(
            stream_request.conversation_id,
            self.thread_manager.user_sub,
        )
        snapshot = await self._load_owned_snapshot(stream_request.conversation_id)
        patch = (
            ChatThreadStatePatch(
                messages=submitted_messages,
                context_file_paths=stream_request.context_file_paths,
                title=(record.title if record is not None else None)
                or derive_title_from_text(submitted_messages[0].content),
                created_at=(
                    self._db_timestamp_to_iso(record.created_at)
                    if record is not None
                    else resolved_now
                ),
                updated_at=resolved_now,
                user_sub=self.thread_manager.user_sub,
            )
            if snapshot is None
            else ChatThreadStatePatch(
                messages=submitted_messages,
                context_file_paths=stream_request.context_file_paths,
                updated_at=resolved_now,
            )
        )
        await self.thread_manager.update_state(
            stream_request.conversation_id,
            patch,
            as_node=MANUAL_THREAD_UPDATE_NODE,
        )

    async def append_assistant_message(
        self,
        conversation_id: str,
        message: AIMessage,
        *,
        updated_at: str | None = None,
    ) -> None:
        """Append one assistant message to a persisted conversation thread."""
        resolved_updated_at = updated_at or iso_now()
        record = await self.record_service.get_owned_conversation(
            conversation_id,
            self.thread_manager.user_sub,
        )
        if record is None:
            raise ValueError("Conversation not found")

        snapshot = await self._load_owned_snapshot(conversation_id)
        patch = (
            ChatThreadStatePatch(
                messages=[message],
                context_file_paths=[],
                title=record.title,
                created_at=self._db_timestamp_to_iso(record.created_at),
                updated_at=resolved_updated_at,
                user_sub=self.thread_manager.user_sub,
            )
            if snapshot is None
            else ChatThreadStatePatch(
                messages=[message],
                updated_at=resolved_updated_at,
            )
        )
        await self.thread_manager.update_state(
            conversation_id,
            patch,
            as_node=MANUAL_THREAD_UPDATE_NODE,
        )
        await self.record_service.upsert_conversation(
            conversation_id=conversation_id,
            user_sub=self.thread_manager.user_sub,
            title=record.title,
            created_at=record.created_at,
            updated_at=resolved_updated_at,
        )

    async def prepare_message_regeneration(
        self,
        conversation_id: str,
        message_id: str,
        *,
        now: str | None = None,
    ) -> ConversationRegenerationRequest | None:
        """Rewind the latest assistant answer and prepare its user prompt for rerun."""
        resolved_now = now or iso_now()
        record = await self.record_service.get_owned_conversation(
            conversation_id,
            self.thread_manager.user_sub,
        )
        if record is None:
            return None

        snapshot = await self._load_owned_snapshot(conversation_id)
        if snapshot is None:
            raise ValueError("Conversation has no messages")

        visible_messages: list[tuple[int, str, AnyMessage]] = []
        for index, message in enumerate(snapshot.messages):
            role = self._visible_message_role(message)
            if role is not None:
                visible_messages.append((index, role, message))

        target_visible_index = next(
            (
                index
                for index, (_, _, message) in enumerate(visible_messages)
                if str(getattr(message, "id", "")) == message_id
            ),
            None,
        )
        if target_visible_index is None:
            raise ValueError("Message not found")

        target_raw_index, target_role, _ = visible_messages[target_visible_index]
        if target_role != "assistant":
            raise ValueError("Only assistant messages can be regenerated")
        if target_visible_index != len(visible_messages) - 1:
            raise ValueError("Only the latest assistant message can be regenerated")
        if target_visible_index == 0:
            raise ValueError("Assistant message has no preceding user message")

        _, preceding_role, preceding_message = visible_messages[
            target_visible_index - 1
        ]
        if preceding_role != "user":
            raise ValueError("Assistant message has no preceding user message")

        prompt = self._message_text(preceding_message)
        if not prompt.strip():
            raise ValueError("Preceding user message is empty")

        messages_to_remove = snapshot.messages[target_raw_index:]
        remove_messages: list[RemoveMessage] = []
        for message in messages_to_remove:
            persisted_id = getattr(message, "id", None)
            if not persisted_id:
                raise ValueError("Cannot regenerate a message without persisted ids")
            remove_messages.append(RemoveMessage(id=str(persisted_id)))

        preceding_kwargs = self._message_additional_kwargs(preceding_message)
        context_file_paths = normalize_context_file_paths(
            preceding_kwargs.get("context_file_paths")
        ) or list(snapshot.context_file_paths)

        await self.thread_manager.update_state(
            conversation_id,
            ChatThreadStatePatch(
                messages=remove_messages,
                context_file_paths=context_file_paths,
                updated_at=resolved_now,
            ),
            as_node=REGENERATION_REWIND_NODE,
        )
        await self.record_service.upsert_conversation(
            conversation_id=conversation_id,
            user_sub=self.thread_manager.user_sub,
            title=record.title,
            created_at=record.created_at,
            updated_at=resolved_now,
        )

        return ConversationRegenerationRequest(
            messages=[
                ChatStreamMessage(
                    id=str(getattr(preceding_message, "id", "") or uuid4()),
                    type="human",
                    content=prompt,
                    additional_kwargs={
                        "created_at": preceding_kwargs.get("created_at")
                        or resolved_now,
                    },
                )
            ],
            context_file_paths=context_file_paths,
        )

    async def import_transcript(
        self,
        *,
        messages: list[ChatStreamMessage],
        context_file_paths: list[str],
        title: str | None = None,
        now: str | None = None,
    ) -> str:
        """Materialize one temporary UI transcript as a persisted conversation."""
        resolved_now = now or iso_now()
        normalized_context_paths = normalize_context_file_paths(context_file_paths)
        transcript_messages = build_transcript_messages(
            messages,
            context_file_paths=normalized_context_paths,
        )
        if not transcript_messages:
            raise ValueError("messages must include at least one user message")
        first_human_message = next(
            (
                message
                for message in transcript_messages
                if getattr(message, "type", None) == "human"
            ),
            None,
        )
        if first_human_message is None:
            raise ValueError("messages must include at least one user message")

        conversation_id = str(uuid4())
        resolved_title = title or derive_title_from_text(
            str(first_human_message.content)
        )
        await self.record_service.upsert_conversation(
            conversation_id=conversation_id,
            user_sub=self.thread_manager.user_sub,
            title=resolved_title,
            created_at=resolved_now,
            updated_at=resolved_now,
        )
        await self.thread_manager.update_state(
            conversation_id,
            ChatThreadStatePatch(
                messages=transcript_messages,
                context_file_paths=normalized_context_paths,
                title=resolved_title,
                created_at=resolved_now,
                updated_at=resolved_now,
                user_sub=self.thread_manager.user_sub,
            ),
            as_node=MANUAL_THREAD_UPDATE_NODE,
        )
        return conversation_id

    async def list_conversations(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[ConversationSummary], int]:
        user_sub = self.thread_manager.user.normalized_sub
        records = (
            await self.record_service.list_owned_conversations(user_sub)
            if user_sub
            else []
        )

        active_runs = (
            {
                run.conversation_id: run
                for run in await ChatRunService(
                    self.thread_manager.db
                ).list_active_runs_for_user(user_sub)
            }
            if user_sub
            else {}
        )
        summaries: list[ConversationSummary] = []

        for record in records:
            active_run = active_runs.get(record.id)
            updated_at = self._db_timestamp_to_iso(record.updated_at)
            if active_run is not None:
                updated_at = max(
                    updated_at,
                    self._db_timestamp_to_iso(active_run.updated_at),
                    key=self._updated_at_as_utc,
                )

            summary = self._record_summary(
                record,
                active_run_status=active_run.status if active_run is not None else None,
            )
            summary.updated_at = updated_at
            summaries.append(summary)

        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        total = len(summaries)
        return summaries[offset : offset + limit], total

    async def list_conversation_ids(self) -> list[str]:
        conversations, _ = await self.list_conversations(limit=10_000, offset=0)
        return [conversation.id for conversation in conversations]

    async def list_conversation_ids_before(self, before: datetime) -> list[str]:
        conversations, _ = await self.list_conversations(limit=10_000, offset=0)
        cutoff = (
            before if before.tzinfo is not None else before.replace(tzinfo=timezone.utc)
        )
        return [
            conversation.id
            for conversation in conversations
            if self._updated_at_as_utc(conversation.updated_at) < cutoff
        ]

    async def get_conversation(self, conversation_id: str) -> ConversationDetail | None:
        user_sub = self.thread_manager.user_sub
        record = await self.record_service.get_owned_conversation(
            conversation_id, user_sub
        )
        if record is None:
            return None
        snapshot = await self._load_owned_snapshot(conversation_id)
        if snapshot is None:
            return self._record_detail(record)
        return build_conversation_detail(
            conversation_id,
            snapshot,
            title=record.title,
            created_at=self._db_timestamp_to_iso(record.created_at),
            updated_at=self._db_timestamp_to_iso(record.updated_at),
        )

    async def exists_for_user(self, conversation_id: str) -> bool:
        return (
            await self.record_service.get_owned_conversation(
                conversation_id,
                self.thread_manager.user_sub,
            )
            is not None
        )

    async def update_conversation(
        self, conversation_id: str, title: str | None
    ) -> ConversationSummary | None:
        user_sub = self.thread_manager.user_sub
        record = await self.record_service.get_owned_conversation(
            conversation_id, user_sub
        )
        if record is None:
            return None

        updated_at = iso_now()
        snapshot = await self._load_owned_snapshot(conversation_id)
        if snapshot is not None:
            await self.thread_manager.update_state(
                conversation_id,
                build_title_state_update(title=title, updated_at=updated_at),
                as_node=MANUAL_THREAD_UPDATE_NODE,
            )

        updated_record = await self.record_service.update_title(
            conversation_id=conversation_id,
            user_sub=user_sub,
            title=title,
            updated_at=updated_at,
        )
        if updated_record is None:
            return None
        return self._record_summary(updated_record)

    async def delete_conversation(self, conversation_id: str) -> bool:
        user_sub = self.thread_manager.user_sub
        record = await self.record_service.get_owned_conversation(
            conversation_id, user_sub
        )
        if record is None:
            return False

        snapshot = await self._load_owned_snapshot(conversation_id)
        if snapshot is not None:
            await self.thread_manager.delete_thread(conversation_id)
        await self.record_service.delete_owned_conversation(conversation_id, user_sub)
        return True

    async def delete_conversations_by_ids(self, conversation_ids: list[str]) -> int:
        deleted = 0
        for conversation_id in dict.fromkeys(conversation_ids):
            if await self.delete_conversation(conversation_id):
                deleted += 1
        return deleted
