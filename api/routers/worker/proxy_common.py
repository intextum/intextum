"""Shared worker proxy authorization helpers."""

import json
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.enums import TaskStatus
from models.sqlalchemy_models import IndexedContentItem
from services.ai_settings import AiSettingsService
from services.task_queue import TaskQueueService
from rls import set_rls_context, worker_task_context
from .helpers import get_task_secret_header
from .proxy_helpers import _effective_registry_model_ids, _validate_worker_texts


def _sse_error_event(
    *,
    message: str,
    error_type: str,
    status_code: int | None = None,
) -> bytes:
    payload: dict[str, Any] = {
        "error": {
            "message": message,
            "type": error_type,
        }
    }
    if status_code is not None:
        payload["error"]["status_code"] = status_code
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


def _ok_response(**values: int) -> dict[str, object]:
    return {"status": "ok", **values}


async def _require_existing_content_item_ids(
    db: AsyncSession,
    content_item_ids: set[str],
    *,
    task_secret: str,
    worker_id: str,
) -> None:
    if not content_item_ids:
        return
    result = await db.execute(
        select(IndexedContentItem.content_item_id).where(
            IndexedContentItem.content_item_id.in_(content_item_ids)
        )
    )
    existing_ids = set(result.scalars().all())
    missing_ids = sorted(content_item_ids - existing_ids)
    if missing_ids:
        task_queue = TaskQueueService(db)
        restored_ids: set[str] = set()
        for content_item_id in missing_ids:
            restored = await task_queue.restore_claimed_process_content_item(
                content_item_id=content_item_id,
                task_secret=task_secret,
                worker_id=worker_id,
            )
            if restored:
                restored_ids.add(content_item_id)
        missing_ids = sorted(set(missing_ids) - restored_ids)

    if missing_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cannot upsert chunks for missing content item",
                "content_item_ids": missing_ids,
            },
        )


async def _authorize_registry_model_request(
    task_id: str,
    model_id: str,
    request: Request,
    *,
    db: AsyncSession,
    worker_id: str,
):
    await _authorize_claimed_process_task_id(
        task_id, request, db=db, worker_id=worker_id
    )
    ai_settings = await AiSettingsService(db).get_effective_settings()
    if model_id not in _effective_registry_model_ids(ai_settings):
        raise HTTPException(
            status_code=403,
            detail="Registry model is not referenced by effective worker config",
        )


async def _authorize_claimed_process_task_id(
    task_id: str,
    request: Request,
    *,
    db: AsyncSession,
    worker_id: str,
):
    """Resolve one claimed process task from a path task id and task secret."""
    task_secret = get_task_secret_header(request)
    task = await TaskQueueService(db).get_authorized_task(
        task_id, task_secret, worker_id=worker_id
    )
    if (
        task is None
        or task.task_type != "process"
        or not isinstance(task.content_item_id, str)
        or not task.content_item_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Task secret does not match any active processing task",
        )
    if task.status != TaskStatus.CLAIMED:
        raise HTTPException(
            status_code=409,
            detail=f"Processing task is no longer active: {task.status}",
        )
    await set_rls_context(
        db,
        worker_task_context(
            worker_id=worker_id,
            task_id=task_id,
            content_item_id=task.content_item_id,
        ),
    )
    return task


async def _validated_worker_texts_for_task(
    *,
    task_id: str,
    raw_request: Request,
    db: AsyncSession,
    worker_id: str,
    raw_texts: list[str],
) -> tuple[object, list[str]]:
    settings = get_settings()
    texts = _validate_worker_texts(raw_texts, settings)
    await _authorize_claimed_process_task_id(
        task_id, raw_request, db=db, worker_id=worker_id
    )
    return settings, texts
