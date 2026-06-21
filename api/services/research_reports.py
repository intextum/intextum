"""Persistence helpers for deep research reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import ConversationRunMode
from models.enums import ResearchRunStatus
from models.research import (
    ResearchReportDetail,
    ResearchReportImage,
    ResearchReportListResponse,
    ResearchReportSection,
    ResearchReportSource,
    ResearchReportSummary,
    ResearchVerification,
)
from models.sqlalchemy_models import ChatRun, ResearchReport
from services.utils import utcnow

TReportModel = TypeVar("TReportModel", bound=BaseModel)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _model_list(value: Any, model: type[TReportModel]) -> list[TReportModel]:
    if not isinstance(value, list):
        return []
    return [model.model_validate(item) for item in value if isinstance(item, dict)]


class ResearchReportService:
    """CRUD helpers for persisted research report artifacts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_report(self, report_id: str) -> ResearchReport | None:
        result = await self.db.execute(
            select(ResearchReport).where(ResearchReport.id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _mark_terminal(
        report: ResearchReport,
        *,
        status: ResearchRunStatus,
        now: datetime,
        error_message: str | None = None,
    ) -> None:
        report.status = status.value
        report.error_message = error_message
        report.finished_at = now
        report.updated_at = now

    @staticmethod
    def _summary_from_row(report: ResearchReport) -> ResearchReportSummary:
        return ResearchReportSummary(
            id=report.id,
            title=report.title,
            prompt=report.prompt,
            status=ResearchRunStatus(report.status),
            created_at=_iso(report.created_at) or "",
            updated_at=_iso(report.updated_at) or "",
            finished_at=_iso(report.finished_at),
        )

    @staticmethod
    def _detail_from_row(
        report: ResearchReport,
        *,
        run_id: str | None = None,
    ) -> ResearchReportDetail:
        return ResearchReportDetail(
            id=report.id,
            title=report.title,
            prompt=report.prompt,
            status=ResearchRunStatus(report.status),
            context_file_paths=_string_list(report.context_file_paths_json),
            outline=_string_list(report.outline_json),
            sections=_model_list(report.sections_json, ResearchReportSection),
            sources=_model_list(report.sources_json, ResearchReportSource),
            images=_model_list(report.images_json, ResearchReportImage),
            verification=ResearchVerification(
                issues=_string_list(report.verification_json)
            ),
            content_markdown=report.content_markdown,
            error_message=report.error_message,
            run_id=run_id,
            created_at=_iso(report.created_at) or "",
            updated_at=_iso(report.updated_at) or "",
            finished_at=_iso(report.finished_at),
        )

    async def create_report(
        self,
        *,
        conversation_id: str,
        user_sub: str,
        prompt: str,
        context_file_paths: list[str],
        title: str | None = None,
    ) -> ResearchReport:
        """Create one pending research report artifact."""
        now = utcnow()
        report = ResearchReport(
            id=f"report_{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            user_sub=user_sub,
            title=title,
            prompt=prompt,
            status=ResearchRunStatus.PENDING.value,
            context_file_paths_json=list(context_file_paths),
            outline_json=[],
            sections_json=[],
            sources_json=[],
            images_json=[],
            verification_json=[],
            created_at=now,
            updated_at=now,
        )
        self.db.add(report)
        await self.db.commit()
        return report

    async def get_owned_report_row(
        self,
        report_id: str,
        user_sub: str,
    ) -> ResearchReport | None:
        """Return one report row only when it belongs to the user."""
        result = await self.db.execute(
            select(ResearchReport).where(
                ResearchReport.id == report_id,
                ResearchReport.user_sub == user_sub,
            )
        )
        return result.scalar_one_or_none()

    async def _latest_run_id_for_report(self, report_id: str) -> str | None:
        result = await self.db.execute(
            select(ChatRun.id)
            .where(
                ChatRun.research_report_id == report_id,
                ChatRun.mode == ConversationRunMode.RESEARCH.value,
            )
            .order_by(ChatRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def to_message_metadata(
        self,
        report: ResearchReport,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Convert one report row into the assistant-message metadata shape."""
        detail = self._detail_from_row(report, run_id=run_id)
        metadata = detail.model_dump(mode="json")
        metadata["kind"] = "research_report"
        metadata["report_id"] = report.id
        metadata["conversation_id"] = report.conversation_id
        return metadata

    async def get_owned_report(
        self,
        report_id: str,
        user_sub: str,
    ) -> ResearchReportDetail | None:
        """Return one detailed report for the supplied user."""
        report = await self.get_owned_report_row(report_id, user_sub)
        if report is None:
            return None
        return self._detail_from_row(
            report,
            run_id=await self._latest_run_id_for_report(report_id),
        )

    async def list_owned_reports(
        self,
        user_sub: str,
        *,
        limit: int,
        offset: int,
    ) -> ResearchReportListResponse:
        """Return paginated report summaries for one user."""
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(ResearchReport)
                .where(ResearchReport.user_sub == user_sub)
            )
        ).scalar_one()
        rows = (
            (
                await self.db.execute(
                    select(ResearchReport)
                    .where(ResearchReport.user_sub == user_sub)
                    .order_by(
                        ResearchReport.updated_at.desc(),
                        ResearchReport.created_at.desc(),
                    )
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return ResearchReportListResponse(
            reports=[self._summary_from_row(row) for row in rows],
            total=int(total or 0),
        )

    async def mark_running(self, report_id: str) -> ResearchReport | None:
        """Mark one report as actively running."""
        report = await self._get_report(report_id)
        if report is None:
            return None
        report.status = ResearchRunStatus.RUNNING.value
        report.error_message = None
        report.updated_at = utcnow()
        await self.db.commit()
        return report

    async def mark_completed(
        self,
        report_id: str,
        *,
        title: str | None,
        outline: list[str],
        sections: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        images: list[dict[str, Any]],
        verification_issues: list[str],
        content_markdown: str,
    ) -> ResearchReport | None:
        """Persist the completed report artifact for one finished run."""
        report = await self._get_report(report_id)
        if report is None:
            return None

        now = utcnow()
        report.title = title or report.title
        report.outline_json = list(outline)
        report.sections_json = list(sections)
        report.sources_json = list(sources)
        report.images_json = list(images)
        report.verification_json = list(verification_issues)
        report.content_markdown = content_markdown
        self._mark_terminal(report, status=ResearchRunStatus.COMPLETED, now=now)
        await self.db.commit()
        return report

    async def mark_failed(
        self,
        report_id: str,
        *,
        error_message: str,
    ) -> ResearchReport | None:
        """Mark one report as failed."""
        report = await self._get_report(report_id)
        if report is None:
            return None

        self._mark_terminal(
            report,
            status=ResearchRunStatus.FAILED,
            now=utcnow(),
            error_message=error_message,
        )
        await self.db.commit()
        return report

    async def mark_cancelled(
        self,
        report_id: str,
        *,
        error_message: str | None = None,
    ) -> ResearchReport | None:
        """Mark one report as cancelled."""
        report = await self._get_report(report_id)
        if report is None:
            return None

        self._mark_terminal(
            report,
            status=ResearchRunStatus.CANCELLED,
            now=utcnow(),
            error_message=error_message,
        )
        await self.db.commit()
        return report

    async def delete_report(self, report_id: str) -> bool:
        """Delete one report row by id."""
        report = await self._get_report(report_id)
        if report is None:
            return False

        await self.db.delete(report)
        await self.db.commit()
        return True
