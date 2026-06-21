"""Focused tests for shared file-stats review helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.future import select

from models.sqlalchemy_models import IndexedContentItem
from services.content._stats.review import ReviewQueryHelpers


def _count_result(value: int):
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest.mark.asyncio
async def test_collect_review_summary_returns_bucket_counts():
    """Review helper summary should expose the current bucket counts."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _count_result(7),  # unreviewed
            _count_result(2),  # accepted
            _count_result(1),  # corrected
            _count_result(6),  # dismissed
            _count_result(5),  # needs_review
            _count_result(3),  # missing_required_fields
            _count_result(2),  # conflicted_fields
            _count_result(4),  # missing_evidence
        ]
    )

    summary = await ReviewQueryHelpers.collect_review_summary(
        mock_db,
        select(IndexedContentItem),
        total=10,
        review_reason_codes=(
            "missing_required_fields",
            "conflicted_fields",
            "missing_evidence",
        ),
    )

    assert summary.total == 10
    assert summary.unreviewed == 7
    assert summary.accepted == 2
    assert summary.corrected == 1
    assert summary.dismissed == 6
    assert summary.needs_review == 5
    assert summary.missing_required_fields == 3
    assert summary.conflicted_fields == 2
    assert summary.missing_evidence == 4


def test_review_reason_expr_rejects_unknown_reason():
    """Review helper should reject unsupported reason codes."""
    with pytest.raises(ValueError, match="Unsupported review reason"):
        ReviewQueryHelpers.review_reason_expr("unknown_reason")
