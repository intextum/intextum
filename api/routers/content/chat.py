"""Transient document chat endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from chat.manager import ChatThreadManager
from chat.session import iter_chat_stream_frames, prepare_chat_stream_run
from chat.stream import build_streaming_response
from chat.transport import ChatStreamServiceRequest
from database import get_db
from models.chat import ChatStreamMessage
from models.enums import ConversationRunMode
from models.user import User
from services.ai_settings import AiSettingsService
from services.content import ContentService
from .helpers import (
    get_content_service,
    resolve_authorized_source_file,
)

router = APIRouter()


class ContentChatStreamRequest(BaseModel):
    """Request model for one temporary document chat stream."""

    thread_id: str
    content_path: str
    messages: list[ChatStreamMessage] = Field(default_factory=list)


@router.post("/chat/stream")
async def stream_content_chat(
    body: ContentChatStreamRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    file_service: ContentService = Depends(get_content_service),
):
    """Stream a document-scoped chat response without persisting conversation state."""
    try:
        user.require_stable_sub()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication subject missing",
        ) from exc

    await resolve_authorized_source_file(body.content_path, user, file_service)
    ai_settings = await AiSettingsService(db).get_effective_settings()
    stream_request = ChatStreamServiceRequest(
        conversation_id=body.thread_id,
        messages=body.messages,
        context_file_paths=[body.content_path],
        mode=ConversationRunMode.CHAT,
    )
    thread_manager = ChatThreadManager(
        db=db,
        user=user,
        context_file_paths=stream_request.context_file_paths,
        ai_settings=ai_settings,
        persist_checkpoints=False,
    )
    prepared_run = await prepare_chat_stream_run(
        thread_manager=thread_manager,
        stream_request=stream_request,
        load_existing_snapshot=False,
        use_full_transcript=True,
    )
    return build_streaming_response(iter_chat_stream_frames(prepared_run))
