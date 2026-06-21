"""Tests for durable content audit helpers and endpoint wiring."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from auth.dependencies import require_user
from models.content.audit import ContentAuditEventListResponse
from models.sqlalchemy_models import ContentAuditEvent, IndexedContentItem
from models.user import User
from services.content.audit import ContentAuditService
from services.content.indexed_content_item import upsert_indexed_content_item
from services.utils import compute_content_item_id


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ExecuteResult:
    def __init__(self, *, scalar_value=None, rows=None):
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self):
        return self._scalar_value

    def scalar_one_or_none(self):
        return self._scalar_value

    def scalars(self):
        return _ScalarRows(self._rows)


class _FakeDb:
    def __init__(self, execute_results=None):
        self.added = []
        self.commits = 0
        self.flushes = 0
        self.execute_results = list(execute_results or [])

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1

    async def execute(self, _stmt):
        return self.execute_results.pop(0)


def _record() -> IndexedContentItem:
    return IndexedContentItem(
        content_item_id="item-1",
        folder_uuid="connector-1",
        relative_path="invoices/a.pdf",
        display_name="a.pdf",
        name="a.pdf",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=10,
        is_dir=False,
        is_hidden=False,
        is_symlink=False,
    )


@pytest.mark.asyncio
async def test_append_event_stores_safe_summary_metadata_and_actor():
    db = _FakeDb()
    user = User(
        username="alice",
        sub="sub-alice",
        preferred_username="Alice Reviewer",
    )

    event = await ContentAuditService(db).append_for_record(
        _record(),
        event_type="content.enrichment.classification_corrected",
        event_group="enrichment",
        status="completed",
        summary="Classification corrected to Invoice",
        metadata={
            "classification_label": "Invoice",
            "raw_text": "x" * 800,
            "fields": [f"field_{index}" for index in range(30)],
        },
        user=user,
    )

    assert len(db.added) == 1
    row = db.added[0]
    assert row.content_item_id == "item-1"
    assert row.connector_uuid == "connector-1"
    assert row.metadata_json["classification_label"] == "Invoice"
    assert row.metadata_json["raw_text"].endswith("...")
    assert len(row.metadata_json["fields"]) == 20
    assert event.actor_sub == "sub-alice"
    assert event.actor_name == "Alice Reviewer"
    assert db.flushes == 0
    assert db.commits == 0


@pytest.mark.asyncio
async def test_new_indexed_content_item_appends_created_audit_event():
    db = _FakeDb([_ExecuteResult(scalar_value=None)])

    await upsert_indexed_content_item(
        db,
        "item-1",
        "connector-1",
        "invoices/a.pdf",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=10,
        auto_commit=False,
    )

    content_rows = [row for row in db.added if isinstance(row, IndexedContentItem)]
    audit_rows = [row for row in db.added if isinstance(row, ContentAuditEvent)]
    assert len(content_rows) == 1
    assert len(audit_rows) == 1
    assert audit_rows[0].event_type == "content.created"
    assert audit_rows[0].content_item_id == "item-1"
    assert audit_rows[0].metadata_json["content_kind"] == "file"


@pytest.mark.asyncio
async def test_list_for_content_item_returns_paginated_events():
    created = datetime.fromisoformat("2026-04-29T12:00:00")
    row = ContentAuditEvent(
        id="event-1",
        content_item_id="item-1",
        event_type="content.uploaded",
        event_group="content",
        status="completed",
        summary="Uploaded a.pdf",
        metadata_json={"size_bytes": 10},
        source="ui",
        created_at=created,
    )
    db = _FakeDb(
        [
            _ExecuteResult(scalar_value=1),
            _ExecuteResult(rows=[row]),
        ]
    )

    result = await ContentAuditService(db).list_for_content_item(
        "item-1", limit=10, offset=0
    )

    assert result.total == 1
    assert result.limit == 10
    assert result.offset == 0
    assert result.events[0].id == "event-1"
    assert result.events[0].metadata == {"size_bytes": 10}


def test_content_audit_endpoint_returns_accessible_events(test_client):
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    response_payload = ContentAuditEventListResponse(
        events=[],
        total=0,
        limit=25,
        offset=5,
    )
    try:
        with (
            patch(
                "routers.content.audit.resolve_authorized_source_file",
                new=AsyncMock(
                    return_value=(
                        SimpleNamespace(uuid="connector-1"),
                        "invoices/a.pdf",
                    )
                ),
            ) as mock_resolve,
            patch(
                "routers.content.audit.get_record",
                new=AsyncMock(return_value=_record()),
            ),
            patch(
                "routers.content.audit.ContentAuditService.list_for_content_item",
                new=AsyncMock(return_value=response_payload),
            ) as mock_list,
        ):
            response = test_client.get(
                "/api/content/audit/documents/invoices/a.pdf?limit=25&offset=5"
            )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert response.json()["total"] == 0
    mock_resolve.assert_awaited_once()
    assert mock_resolve.await_args.args[1] is user
    mock_list.assert_awaited_once_with(
        compute_content_item_id("connector-1", "invoices/a.pdf"),
        limit=25,
        offset=5,
    )


def test_content_audit_endpoint_returns_404_for_missing_record(test_client):
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with (
            patch(
                "routers.content.audit.resolve_authorized_source_file",
                new=AsyncMock(
                    return_value=(
                        SimpleNamespace(uuid="connector-1"),
                        "invoices/a.pdf",
                    )
                ),
            ),
            patch("routers.content.audit.get_record", new=AsyncMock(return_value=None)),
        ):
            response = test_client.get("/api/content/audit/documents/invoices/a.pdf")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 404


def test_content_audit_endpoint_preserves_access_denials(test_client):
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "routers.content.audit.resolve_authorized_source_file",
            new=AsyncMock(side_effect=HTTPException(status_code=403, detail="denied")),
        ):
            response = test_client.get("/api/content/audit/documents/invoices/a.pdf")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 403
