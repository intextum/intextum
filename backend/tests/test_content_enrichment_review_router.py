"""Router-level tests for the unified review endpoint."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.content.items import ContentItemInfo
from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem


def _file_info() -> ContentItemInfo:
    return ContentItemInfo(
        id="file-1",
        name="file.pdf",
        display_name="file.pdf",
        path="docs/file.pdf",
        modified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _record_with_state(state_kwargs=None) -> IndexedContentItem:
    state = ContentItemEnrichmentState(content_item_id="file-1", **(state_kwargs or {}))
    record = IndexedContentItem(
        content_item_id="file-1",
        is_dir=False,
        folder_uuid="folder-1",
        relative_path="docs/file.pdf",
        name="file.pdf",
        display_name="file.pdf",
    )
    record.enrichment_state = state
    return record


def _patch_router(record: IndexedContentItem):
    folder = MagicMock()
    folder.uuid = "folder-1"
    folder.immutable = False
    return [
        patch(
            "routers.content.enrichment.resolve_authorized_source_file",
            new=AsyncMock(return_value=(folder, "docs/file.pdf")),
        ),
        patch(
            "routers.content.enrichment.get_record",
            new=AsyncMock(return_value=record),
        ),
        patch(
            "routers.content.enrichment.AiSettingsService",
            return_value=MagicMock(get_effective_settings=AsyncMock(return_value=None)),
        ),
        patch(
            "routers.content.enrichment.record_to_file_info",
            return_value=_file_info(),
        ),
    ]


@pytest.fixture
def patched_submit():
    with patch(
        "routers.content.enrichment.submit_content_enrichment_review",
        new=AsyncMock(),
    ) as mock:
        mock.return_value = _record_with_state()
        yield mock


def test_review_rejects_label_and_dismissed_classification_together(
    test_client, patched_submit
):
    record = _record_with_state()
    with (
        _patch_router(record)[0],
        _patch_router(record)[1],
        _patch_router(record)[2],
        _patch_router(record)[3],
    ):
        response = test_client.post(
            "/api/content/review/docs/file.pdf",
            json={
                "classification_label": "Permit",
                "classification_dismissed": True,
                "classification_dismiss_reason": "no_fitting_class",
            },
        )
    assert response.status_code == 400
    assert "mutually exclusive" in response.json()["detail"]
    patched_submit.assert_not_awaited()


def test_review_rejects_data_and_dismissed_extraction_together(
    test_client, patched_submit
):
    record = _record_with_state()
    with (
        _patch_router(record)[0],
        _patch_router(record)[1],
        _patch_router(record)[2],
        _patch_router(record)[3],
    ):
        response = test_client.post(
            "/api/content/review/docs/file.pdf",
            json={
                "extraction_data": {"foo": "bar"},
                "extraction_dismissed": True,
                "extraction_dismiss_reason": "not_extractable",
            },
        )
    assert response.status_code == 400
    assert "mutually exclusive" in response.json()["detail"]
    patched_submit.assert_not_awaited()


def test_review_dismiss_classification_calls_service(test_client, patched_submit):
    record = _record_with_state()
    with (
        _patch_router(record)[0],
        _patch_router(record)[1],
        _patch_router(record)[2],
        _patch_router(record)[3],
    ):
        response = test_client.post(
            "/api/content/review/docs/file.pdf",
            json={
                "classification_dismissed": True,
                "classification_dismiss_reason": "not_a_document",
            },
        )
    assert response.status_code == 200
    patched_submit.assert_awaited_once()
    kwargs = patched_submit.await_args.kwargs
    assert kwargs["dismiss_classification"] is True
    assert kwargs["classification_dismiss_reason"] == "not_a_document"
    assert kwargs["update_classification"] is False


def test_review_empty_payload_returns_400(test_client):
    record = _record_with_state()
    with (
        _patch_router(record)[0],
        _patch_router(record)[1],
        _patch_router(record)[2],
        _patch_router(record)[3],
    ):
        response = test_client.post(
            "/api/content/review/docs/file.pdf",
            json={},
        )
    assert response.status_code == 400
