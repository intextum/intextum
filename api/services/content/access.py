"""Shared source-path resolution and access checks for file endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from config import BaseDataConnector
from models.sqlalchemy_models import IndexedContentItem
from models.user import User
from services.connector import ConnectorRuntimeService
from services.content.location import split_api_path
from services.utils import compute_content_item_id

from .helpers import (
    get_record,
    resolve_db_context,
    user_can_access_folder_uuid,
    user_can_access_record,
)


@dataclass(frozen=True)
class ResolvedSourceTarget:
    """Resolved source entry plus the indexed record when available."""

    folder: BaseDataConnector
    relative_path: str
    content_item_id: str
    record: IndexedContentItem | None


def _required_source_path(api_path: str) -> str:
    stripped = api_path.strip("/")
    if not stripped:
        raise ValueError("Path is required")
    return stripped


def _not_found_detail(expect_dir: bool) -> str:
    return "Directory not found" if expect_dir else "File not found"


def _type_mismatch_detail(expect_dir: bool) -> str:
    return "Path is not a directory" if expect_dir else "Path is not a file"


def _not_indexed_detail(expect_dir: bool, api_path: str) -> str:
    kind = "Directory" if expect_dir else "File"
    return f"{kind} not indexed: {api_path}"


def _resolve_connector_by_name_any(connector_name: str) -> BaseDataConnector | None:
    for connector in ConnectorRuntimeService().all_connectors():
        if connector.name == connector_name:
            return connector
    return None


async def _resolve_indexed_hidden_target(
    db: AsyncSession,
    api_path: str,
    user: User | None,
    *,
    expect_dir: bool,
) -> ResolvedSourceTarget | None:
    connector_name, connector_rel_path = split_api_path(api_path)
    connector = _resolve_connector_by_name_any(connector_name)
    if connector is None or getattr(connector, "browsable", True):
        return None

    content_item_id = compute_content_item_id(connector.uuid, connector_rel_path)
    record = await get_record(db, content_item_id)
    if record is None:
        return None
    if not user_can_access_record(record, user):
        raise FileNotFoundError(_not_found_detail(expect_dir))
    if record.is_dir != expect_dir:
        raise ValueError(_type_mismatch_detail(expect_dir))
    return ResolvedSourceTarget(
        folder=connector,
        relative_path=record.relative_path,
        content_item_id=content_item_id,
        record=record,
    )


async def _ensure_folder_acl(
    db: AsyncSession,
    folder: BaseDataConnector,
    user: User | None,
    *,
    not_found_detail: str,
) -> None:
    if not await user_can_access_folder_uuid(db, folder.uuid, user):
        raise FileNotFoundError(not_found_detail)


async def resolve_source_target(
    db: AsyncSession,
    api_path: str,
    user: User | None,
    *,
    expect_dir: bool,
    allow_unindexed: bool = True,
) -> ResolvedSourceTarget:
    """Resolve a source API path, enforce ACLs, and optionally require indexing."""

    stripped_path = _required_source_path(api_path)
    not_found_detail = _not_found_detail(expect_dir)
    try:
        folder, folder_rel_path = resolve_db_context(stripped_path)
    except FileNotFoundError as exc:
        await ConnectorRuntimeService(db).refresh()
        try:
            folder, folder_rel_path = resolve_db_context(stripped_path)
        except FileNotFoundError:
            indexed_hidden_target = await _resolve_indexed_hidden_target(
                db,
                stripped_path,
                user,
                expect_dir=expect_dir,
            )
            if indexed_hidden_target is not None:
                return indexed_hidden_target
            raise FileNotFoundError(not_found_detail) from exc
    content_item_id = compute_content_item_id(folder.uuid, folder_rel_path)
    record = await get_record(db, content_item_id)

    if record is not None:
        if not user_can_access_record(record, user):
            raise FileNotFoundError(not_found_detail)
        if record.is_dir != expect_dir:
            raise ValueError(_type_mismatch_detail(expect_dir))
        return ResolvedSourceTarget(
            folder=folder,
            relative_path=record.relative_path,
            content_item_id=content_item_id,
            record=record,
        )

    await _ensure_folder_acl(
        db,
        folder,
        user,
        not_found_detail=not_found_detail,
    )

    adapter = folder.get_adapter()
    if not await adapter.exists(folder_rel_path):
        raise FileNotFoundError(not_found_detail)

    if expect_dir:
        if not await adapter.is_dir(folder_rel_path):
            raise ValueError(_type_mismatch_detail(expect_dir))
    elif not await adapter.is_file(folder_rel_path):
        raise ValueError(_type_mismatch_detail(expect_dir))

    if not allow_unindexed:
        raise FileNotFoundError(_not_indexed_detail(expect_dir, stripped_path))

    return ResolvedSourceTarget(
        folder=folder,
        relative_path=folder_rel_path,
        content_item_id=content_item_id,
        record=None,
    )
