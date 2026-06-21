"""Conversation API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from chat.run.service import ActiveChatRunExistsError, ChatRunService
from database import get_db
from models.chat.runs import ChatRunRequestPayload, CreateChatRunResponse
from models.conversation import (
    ConversationBulkDeleteResponse,
    ConversationDetail,
    ConversationImportRequest,
    ConversationImportResponse,
    ConversationListResponse,
    ConversationUpdate,
)
from models.enums import ConversationRunMode
from models.user import User
from services.conversation import ConversationService
from .helpers import get_conversation_service
from .runs import _disabled_runs_detail, _runs_enabled, _user_payload

router = APIRouter()


def _require_user_sub(user: User) -> str:
    """Return the authenticated user's stable subject identifier."""
    try:
        return user.require_stable_sub()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication subject missing",
        ) from e


def _normalize_cutoff_datetime(cutoff: datetime) -> datetime:
    """Normalize datetime query value to naive UTC for DB comparisons."""
    if cutoff.tzinfo is None:
        return cutoff
    return cutoff.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """List the current user's conversations."""
    _require_user_sub(user)
    conversations, total = await service.list_conversations(limit=limit, offset=offset)
    return ConversationListResponse(conversations=conversations, total=total)


@router.post("/import", response_model=ConversationImportResponse)
async def import_conversation(
    body: ConversationImportRequest,
    user: User = Depends(require_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """Persist a temporary chat transcript as a normal conversation."""
    _require_user_sub(user)
    try:
        conversation_id = await service.import_transcript(
            title=body.title,
            messages=body.messages,
            context_file_paths=body.context_file_paths,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return ConversationImportResponse(conversation_id=conversation_id)


@router.delete("/", response_model=ConversationBulkDeleteResponse)
async def delete_all_conversations(
    before: datetime | None = Query(
        default=None,
        description="Delete only conversations with updated_at older than this ISO timestamp.",
    ),
    user: User = Depends(require_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """Delete all conversations for the current user."""
    _require_user_sub(user)
    if before is None:
        conversation_ids = await service.list_conversation_ids()
    else:
        conversation_ids = await service.list_conversation_ids_before(
            _normalize_cutoff_datetime(before)
        )

    deleted_count = await service.delete_conversations_by_ids(conversation_ids)
    return ConversationBulkDeleteResponse(deleted_count=deleted_count)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(require_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """Get a conversation with all its messages."""
    _require_user_sub(user)
    conv = await service.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conv


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    user: User = Depends(require_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """Update a conversation (rename)."""
    _require_user_sub(user)
    conv = await service.update_conversation(conversation_id, title=body.title)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conv


@router.post(
    "/{conversation_id}/messages/{message_id}/regenerate",
    response_model=CreateChatRunResponse,
)
async def regenerate_conversation_message(
    conversation_id: str,
    message_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    service: ConversationService = Depends(get_conversation_service),
):
    """Regenerate the latest assistant response in a normal chat conversation."""
    user_sub = _require_user_sub(user)
    if not _runs_enabled(ConversationRunMode.CHAT):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_disabled_runs_detail(ConversationRunMode.CHAT),
        )

    run_service = ChatRunService(db)
    if await run_service.has_active_run(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation already has an active run",
        )

    try:
        regeneration = await service.prepare_message_regeneration(
            conversation_id,
            message_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if regeneration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    payload = ChatRunRequestPayload(
        conversation_id=conversation_id,
        mode=ConversationRunMode.CHAT,
        user=_user_payload(user),
        messages=regeneration.messages,
        context_file_paths=regeneration.context_file_paths,
    )
    try:
        created = await run_service.create_run(
            conversation_id=conversation_id,
            user_sub=user_sub,
            request_payload=payload.model_dump(mode="json"),
            mode=payload.mode.value,
        )
    except ActiveChatRunExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation already has an active run",
        ) from exc

    return CreateChatRunResponse(
        run_id=created.id,
        conversation_id=created.conversation_id,
        mode=created.mode,
        research_report_id=created.research_report_id,
        status=created.status,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(require_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """Delete a conversation and all its messages."""
    _require_user_sub(user)
    if not await service.delete_conversation(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return None
