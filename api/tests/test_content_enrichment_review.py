"""Tests for content enrichment review helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem
from services.content.enrichment.review import (
    ContentReviewSubmitError,
    _keeps_existing_correction,
    submit_content_enrichment_review,
)


def test_keeps_existing_correction_only_for_matching_corrected_state():
    assert _keeps_existing_correction("corrected", True) is True
    assert _keeps_existing_correction("corrected", False) is False
    assert _keeps_existing_correction("accepted", True) is False
    assert _keeps_existing_correction(None, True) is False


def _make_user():
    user = MagicMock()
    user.display_name = "Reviewer"
    user.normalized_sub = "sub:reviewer"
    return user


def _record_with_state(state_kwargs=None) -> IndexedContentItem:
    state = ContentItemEnrichmentState(content_item_id="file-1", **(state_kwargs or {}))
    record = IndexedContentItem(content_item_id="file-1")
    record.enrichment_state = state
    return record


def _patched_audit():
    return patch(
        "services.content.enrichment.review.ContentAuditService",
        return_value=MagicMock(append_for_record=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_dismiss_classification_clears_effective_and_cascades_to_extraction():
    record = _record_with_state(
        {
            "classification_system_label": "Permit",
            "classification_effective_label": "Permit",
            "extraction_data_json": {"x": 1},
            "extraction_effective_data_json": {"x": 1},
        }
    )
    db = AsyncMock()
    with _patched_audit():
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            classification_dismiss_reason="not_a_document",
            dismiss_classification=True,
        )
    state = record.enrichment_state
    assert state.classification_review_status == "dismissed"
    assert state.classification_dismissed_reason == "not_a_document"
    assert state.classification_effective_label is None
    assert state.classification_effective_class_id is None
    # cascade
    assert state.extraction_review_status == "dismissed"
    assert state.extraction_dismissed_reason == "no_class"
    assert state.extraction_effective_data_json == {}


@pytest.mark.asyncio
async def test_dismiss_extraction_alone_keeps_classification():
    record = _record_with_state(
        {
            "classification_effective_label": "Permit",
            "classification_review_status": "accepted",
            "extraction_effective_data_json": {"x": 1},
        }
    )
    db = AsyncMock()
    with _patched_audit():
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            extraction_dismiss_reason="not_extractable",
            dismiss_extraction=True,
        )
    state = record.enrichment_state
    assert state.classification_review_status == "accepted"
    assert state.classification_effective_label == "Permit"
    assert state.extraction_review_status == "dismissed"
    assert state.extraction_dismissed_reason == "not_extractable"
    assert state.extraction_effective_data_json == {}


@pytest.mark.asyncio
async def test_dismiss_classification_rejects_invalid_reason():
    record = _record_with_state()
    db = AsyncMock()
    with _patched_audit(), pytest.raises(ContentReviewSubmitError):
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            classification_dismiss_reason="bogus",
            dismiss_classification=True,
        )


@pytest.mark.asyncio
async def test_dismiss_extraction_rejects_invalid_reason():
    record = _record_with_state()
    db = AsyncMock()
    with _patched_audit(), pytest.raises(ContentReviewSubmitError):
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            extraction_dismiss_reason="bogus",
            dismiss_extraction=True,
        )


@pytest.mark.asyncio
async def test_accept_after_dismiss_clears_dismissed_reason():
    record = _record_with_state(
        {
            "classification_system_label": "Permit",
            "classification_system_class_id": "permit",
            "classification_review_status": "dismissed",
            "classification_dismissed_reason": "no_fitting_class",
        }
    )
    db = AsyncMock()
    with _patched_audit():
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            classification_label="Permit",
            update_classification=True,
        )
    state = record.enrichment_state
    assert state.classification_review_status == "accepted"
    assert state.classification_dismissed_reason is None
    assert state.classification_effective_label == "Permit"


@pytest.mark.asyncio
async def test_reset_classification_clears_state_and_cascades_to_extraction():
    record = _record_with_state(
        {
            "classification_system_label": "Permit",
            "classification_override_label": "Invoice",
            "classification_effective_label": "Invoice",
            "classification_review_status": "corrected",
            "classification_dismissed_reason": None,
            "extraction_effective_data_json": {"x": 1},
            "extraction_review_status": "accepted",
        }
    )
    db = AsyncMock()
    with _patched_audit():
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            reset_classification=True,
        )
    state = record.enrichment_state
    assert state.classification_review_status is None
    assert state.classification_override_label is None
    assert state.classification_effective_label is None
    assert state.classification_reviewed_by is None
    # cascade: extraction cleared too
    assert state.extraction_review_status is None
    assert state.extraction_effective_data_json == {}
    # system value is retained for re-classification suggestions
    assert state.classification_system_label == "Permit"


@pytest.mark.asyncio
async def test_reset_extraction_alone_keeps_classification():
    record = _record_with_state(
        {
            "classification_effective_label": "Permit",
            "classification_review_status": "accepted",
            "extraction_override_data_json": {"x": 1},
            "extraction_effective_data_json": {"x": 1},
            "extraction_review_status": "corrected",
        }
    )
    db = AsyncMock()
    with _patched_audit():
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            reset_extraction=True,
        )
    state = record.enrichment_state
    assert state.classification_review_status == "accepted"
    assert state.classification_effective_label == "Permit"
    assert state.extraction_review_status is None
    assert state.extraction_override_data_json is None
    assert state.extraction_effective_data_json == {}


@pytest.mark.asyncio
async def test_no_review_data_raises():
    record = _record_with_state()
    db = AsyncMock()
    with _patched_audit(), pytest.raises(ContentReviewSubmitError):
        await submit_content_enrichment_review(db, record, user=_make_user())


@pytest.mark.asyncio
async def test_audit_event_captures_classification_before_after():
    record = _record_with_state(
        {
            "classification_system_label": "Permit",
            "classification_effective_label": "Permit",
        }
    )
    db = AsyncMock()
    audit_mock = MagicMock(append_for_record=AsyncMock())
    with patch(
        "services.content.enrichment.review.ContentAuditService",
        return_value=audit_mock,
    ):
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            classification_label="Planning Document",
            update_classification=True,
        )
    args = audit_mock.append_for_record.await_args
    metadata = args.kwargs["metadata"]
    assert metadata["before_label"] == "Permit"
    assert metadata["after_label"] == "Planning Document"


@pytest.mark.asyncio
async def test_audit_event_captures_extraction_field_changes():
    record = _record_with_state(
        {
            "classification_effective_label": "Invoice",
            "extraction_data_json": {"a": 1, "b": 2},
            "extraction_effective_data_json": {"a": 1, "b": 2},
        }
    )
    db = AsyncMock()
    audit_mock = MagicMock(append_for_record=AsyncMock())
    with patch(
        "services.content.enrichment.review.ContentAuditService",
        return_value=audit_mock,
    ):
        await submit_content_enrichment_review(
            db,
            record,
            user=_make_user(),
            extraction_data={"a": 1, "b": 9, "c": 3},
            update_extraction=True,
        )
    args = audit_mock.append_for_record.await_args
    metadata = args.kwargs["metadata"]
    assert metadata["changed_field_count"] == 2
    assert metadata["field_changes"]["b"] == {"before": 2, "after": 9}
    assert metadata["field_changes"]["c"] == {"before": None, "after": 3}
