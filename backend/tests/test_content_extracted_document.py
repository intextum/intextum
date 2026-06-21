"""Tests for extracted document viewer endpoints."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.user import User
from routers.content.extracted import get_extracted_document_by_id


def _execute_result(value=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _user() -> User:
    return User(
        username="author",
        sub="sub-author",
        groups=["users"],
    )


@pytest.mark.asyncio
async def test_get_extracted_document_by_id_returns_docling_json():
    record = SimpleNamespace(
        content_item_id="content-1",
        document_json={"texts": [{"self_ref": "#/texts/0", "text": "ok"}]},
        allowed_viewers=["sub:sub-author"],
        denied_viewers=None,
    )
    db = AsyncMock()
    db.execute.return_value = _execute_result(record)

    response = await get_extracted_document_by_id("content-1", _user(), db)

    assert json.loads(response.body) == {
        "texts": [{"self_ref": "#/texts/0", "text": "ok"}]
    }


@pytest.mark.asyncio
async def test_get_extracted_document_by_id_adds_meta_annotations():
    record = SimpleNamespace(
        content_item_id="content-1",
        document_json={
            "pictures": [
                {
                    "self_ref": "#/pictures/0",
                    "meta": {
                        "classification": {
                            "predictions": [{"class_name": "chart", "confidence": 0.8}]
                        },
                        "description": {"text": "Energy use chart."},
                    },
                }
            ]
        },
        allowed_viewers=["sub:sub-author"],
        denied_viewers=None,
    )
    db = AsyncMock()
    db.execute.return_value = _execute_result(record)

    response = await get_extracted_document_by_id("content-1", _user(), db)

    payload = json.loads(response.body)
    assert payload["pictures"][0]["annotations"] == [
        {
            "kind": "classification",
            "predicted_classes": [{"class_name": "chart", "confidence": 0.8}],
        },
        {"kind": "description", "text": "Energy use chart."},
    ]


@pytest.mark.asyncio
async def test_get_extracted_document_by_id_enforces_acl():
    record = SimpleNamespace(
        content_item_id="content-1",
        document_json={"texts": []},
        allowed_viewers=["group:admins"],
        denied_viewers=None,
    )
    db = AsyncMock()
    db.execute.return_value = _execute_result(record)

    with pytest.raises(HTTPException) as exc_info:
        await get_extracted_document_by_id("content-1", _user(), db)

    assert exc_info.value.status_code == 403
