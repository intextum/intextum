"""Tests for persisted research report lifecycle transitions."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.enums import ResearchRunStatus
from models.research import ResearchReportSection
from models.sqlalchemy_models import ResearchReport
from services.research_reports import ResearchReportService, _model_list


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc).replace(tzinfo=None)


def _db_with_report(report: ResearchReport | None):
    db = AsyncMock()
    db.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=report)
    )
    return db


def _report() -> ResearchReport:
    return ResearchReport(
        id="report_123",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        title="Draft title",
        prompt="Research prompt",
        status=ResearchRunStatus.RUNNING.value,
        context_file_paths_json=[],
        outline_json=[],
        sections_json=[],
        sources_json=[],
        images_json=[],
        verification_json=[],
        created_at=_utc(2026, 4, 24, 9),
        updated_at=_utc(2026, 4, 24, 9),
    )


def test_model_list_validates_dict_items_only():
    sections = _model_list(
        [
            {"heading": "Summary", "body": "Done."},
            "ignored",
        ],
        ResearchReportSection,
    )

    assert sections == [ResearchReportSection(heading="Summary", body="Done.")]


def test_model_list_returns_empty_list_for_non_list_value():
    assert _model_list({"heading": "Summary"}, ResearchReportSection) == []


@pytest.mark.asyncio
async def test_mark_completed_stores_report_artifact_and_terminal_metadata():
    report = _report()
    db = _db_with_report(report)

    with patch("services.research_reports.utcnow", return_value=_utc(2026, 4, 24, 10)):
        completed = await ResearchReportService(db).mark_completed(
            "report_123",
            title="Final title",
            outline=["Summary"],
            sections=[{"heading": "Summary", "body": "Done."}],
            sources=[{"citation_index": 1, "file_path": "docs/report.pdf"}],
            images=[{"url": "chart.png", "title": "Chart"}],
            verification_issues=["Missing secondary source"],
            content_markdown="# Final title",
        )

    assert completed is report
    assert report.status == ResearchRunStatus.COMPLETED.value
    assert report.title == "Final title"
    assert report.outline_json == ["Summary"]
    assert report.content_markdown == "# Final title"
    assert report.error_message is None
    assert report.finished_at == _utc(2026, 4, 24, 10)
    assert report.updated_at == _utc(2026, 4, 24, 10)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_failed_stores_terminal_error_metadata():
    report = _report()
    db = _db_with_report(report)

    with patch("services.research_reports.utcnow", return_value=_utc(2026, 4, 24, 10)):
        failed = await ResearchReportService(db).mark_failed(
            "report_123",
            error_message="Research generation failed.",
        )

    assert failed is report
    assert report.status == ResearchRunStatus.FAILED.value
    assert report.error_message == "Research generation failed."
    assert report.finished_at == _utc(2026, 4, 24, 10)
    assert report.updated_at == _utc(2026, 4, 24, 10)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_cancelled_returns_none_when_missing():
    db = _db_with_report(None)

    cancelled = await ResearchReportService(db).mark_cancelled(
        "report_missing",
        error_message="Cancelled by user.",
    )

    assert cancelled is None
    db.commit.assert_not_awaited()
