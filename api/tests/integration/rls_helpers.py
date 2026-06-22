"""Shared helpers for service-level RLS integration tests."""

from __future__ import annotations

import os
from typing import Literal

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models.task_queue import EnqueueProcessTask, ProcessTaskMetadata
from models.vector import VectorChunkUpsert
from rls import RlsContext, set_rls_context, worker_claim_context
from services.content.audit import ContentAuditService
from services.content.indexed_content_item import upsert_indexed_content_item
from services.task_queue import TaskQueueService
from services.vector import VectorService


ProcessTaskState = Literal["PENDING", "CLAIMED", "COMPLETED"]


def async_app_url(*, database: str) -> str:
    return URL.create(
        drivername="postgresql+asyncpg",
        username=os.environ.get("POSTGRES_APP_USER", "intextum_app"),
        password=os.environ.get("POSTGRES_APP_PASSWORD", "intextum_app"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=database,
    ).render_as_string(hide_password=False)


def session_factory(*, database: str):
    engine = create_async_engine(async_app_url(database=database))
    return engine, sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def admin_context() -> RlsContext:
    return RlsContext(
        actor="user",
        user_sub="sub-admin",
        trustees=["everyone", "sub:sub-admin", "__acl_admin__"],
        is_admin=True,
    )


def user_context(*, user_sub: str, groups: list[str] | None = None) -> RlsContext:
    trustees = ["everyone", f"sub:{user_sub}"]
    trustees.extend(f"group:{group}" for group in groups or [])
    return RlsContext(actor="user", user_sub=user_sub, trustees=trustees)


def set_psycopg_context(conn, *, actor: str, **overrides: str) -> None:
    values = {
        "user_sub": "",
        "trustees": "[]",
        "is_admin": "false",
        "worker_id": "",
        "task_id": "",
        "content_item_id": "",
        **overrides,
    }
    conn.execute("SELECT set_config('app.actor', %s, true)", (actor,))
    for key, value in values.items():
        conn.execute(f"SELECT set_config('app.{key}', %s, true)", (value,))


def visible_content_ids(
    conn,
    *,
    actor: str = "user",
    user_sub: str = "",
    trustees: str = "[]",
    is_admin: str = "false",
) -> list[str]:
    with conn.transaction():
        set_psycopg_context(
            conn,
            actor=actor,
            user_sub=user_sub,
            trustees=trustees,
            is_admin=is_admin,
        )
        rows = conn.execute(
            """
            SELECT content_item_id
            FROM indexed_content_items
            ORDER BY content_item_id
            """
        ).fetchall()
    return [row[0] for row in rows]


async def append_completed_audit(
    session: AsyncSession,
    *,
    content_item_id: str = "content-1",
    actor_sub: str | None = None,
) -> None:
    await ContentAuditService(session).append_event(
        content_item_id=content_item_id,
        connector_uuid="folder-1",
        relative_path="docs/file.pdf",
        display_name="file.pdf",
        event_type="content.processing.completed",
        event_group="processing",
        status="COMPLETED",
        summary="Processing completed",
        metadata={"source": "integration"},
        actor_sub=actor_sub,
        source="worker",
    )


async def create_indexed_document_with_chunk(
    session: AsyncSession,
    *,
    content_item_id: str,
    folder_uuid: str = "folder-1",
    relative_path: str | None = None,
    allowed_viewers: list[str] | None = None,
    denied_viewers: list[str] | None = None,
    text: str = "Integration document text",
) -> None:
    path = relative_path or f"docs/{content_item_id}.pdf"
    await upsert_indexed_content_item(
        session,
        content_item_id=content_item_id,
        folder_uuid=folder_uuid,
        relative_path=path,
        modified_time=1.0,
        change_time=1.0,
        size_bytes=len(text),
        status="COMPLETED",
        allowed_viewers=allowed_viewers,
        denied_viewers=denied_viewers,
        display_name=path.rsplit("/", 1)[-1],
    )
    await VectorService.upsert_chunks(
        session,
        content_item_id,
        [
            VectorChunkUpsert(
                id=f"{content_item_id}:chunk-0",
                text=text,
                embedding=[0.01] * 1024,
                chunk_index=0,
                index_version="integration-v1",
            )
        ],
    )


async def enqueue_process_document(
    session: AsyncSession,
    *,
    content_item_id: str = "content-1",
    relative_path: str = "docs/file.pdf",
    requested_by_sub: str | None = "sub-admin",
) -> str:
    return await TaskQueueService(session).enqueue_process(
        EnqueueProcessTask(
            content_item_id=content_item_id,
            folder_uuid="folder-1",
            relative_path=relative_path,
            metadata=ProcessTaskMetadata(
                content_item_id=content_item_id,
                modified_time=1.0,
                created_time=1.0,
                size_bytes=5,
                allowed_viewers=["everyone"],
            ),
            requested_by_sub=requested_by_sub,
        )
    )


async def enqueue_process_document_as_admin(
    session: AsyncSession,
    *,
    content_item_id: str = "content-1",
) -> str:
    await set_rls_context(session, admin_context())
    return await enqueue_process_document(session, content_item_id=content_item_id)


async def claim_process_document(
    session: AsyncSession,
    *,
    worker_id: str = "worker-1",
):
    await set_rls_context(session, worker_claim_context(worker_id))
    claimed = await TaskQueueService(session).claim_task(worker_id, ["document"])
    assert claimed is not None
    assert claimed.task_secret
    return claimed


async def create_process_task_state(
    database: str,
    *,
    state: ProcessTaskState,
    content_item_id: str = "content-1",
    worker_id: str = "worker-1",
):
    engine, factory = session_factory(database=database)
    try:
        async with factory() as session:
            await enqueue_process_document_as_admin(
                session, content_item_id=content_item_id
            )
            if state == "PENDING":
                return None
            claimed = await claim_process_document(session, worker_id=worker_id)
            if state == "CLAIMED":
                return claimed
            completed = await TaskQueueService(session).complete_task(
                claimed.task_id,
                claimed.task_secret,
                worker_id=worker_id,
            )
            assert completed is True
            return claimed
    finally:
        await engine.dispose()
