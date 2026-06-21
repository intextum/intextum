"""Review expressions and summary collectors for flat file stats."""

from __future__ import annotations

from sqlalchemy import Integer, and_, case, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from models.content.items import ReviewQueueSummary, ReviewReasonFacet
from models.sqlalchemy_models import ContentItemEnrichmentState

from ..enrichment import query_expressions
from .extraction_facets import ExtractionFacetHelpers


class ReviewQueryHelpers:
    """Shared review-state expressions and collectors."""

    @staticmethod
    def review_status_expr(column_name: str):
        """Return one normalized review-status expression."""
        return query_expressions.review_status_expr(column_name)

    @staticmethod
    def has_effective_extraction_expr():
        """Return whether one file has effective extraction data."""
        return query_expressions.has_effective_extraction_expr()

    @staticmethod
    def jsonb_object_key_count_expr(value):
        """Count the keys in one JSON object expression."""
        return query_expressions.jsonb_object_key_count_expr(value)

    @classmethod
    def unreviewed_enrichment_expr(cls):
        """Return files with unreviewed classification or extraction output."""
        classification_review_status = cls.review_status_expr(
            "classification_review_status"
        )
        extraction_review_status = cls.review_status_expr("extraction_review_status")
        return or_(
            and_(
                ExtractionFacetHelpers.effective_document_class_expr().is_not(None),
                classification_review_status.is_(None),
            ),
            and_(
                cls.has_effective_extraction_expr(),
                extraction_review_status.is_(None),
            ),
        )

    @classmethod
    def accepted_enrichment_expr(cls):
        """Return files with accepted enrichment and no corrected review state."""
        classification_review_status = cls.review_status_expr(
            "classification_review_status"
        )
        extraction_review_status = cls.review_status_expr("extraction_review_status")
        has_effective_result = or_(
            ExtractionFacetHelpers.effective_document_class_expr().is_not(None),
            cls.has_effective_extraction_expr(),
        )
        return and_(
            has_effective_result,
            or_(
                classification_review_status.is_(None),
                classification_review_status != "corrected",
            ),
            or_(
                extraction_review_status.is_(None),
                extraction_review_status != "corrected",
            ),
            ~cls.unreviewed_enrichment_expr(),
            or_(
                classification_review_status == "accepted",
                extraction_review_status == "accepted",
            ),
        )

    @classmethod
    def corrected_enrichment_expr(cls):
        """Return files with corrected classification or extraction review state."""
        classification_review_status = cls.review_status_expr(
            "classification_review_status"
        )
        extraction_review_status = cls.review_status_expr("extraction_review_status")
        return or_(
            classification_review_status == "corrected",
            extraction_review_status == "corrected",
        )

    @classmethod
    def dismissed_enrichment_expr(cls):
        """Return files where either review side was dismissed."""
        classification_review_status = cls.review_status_expr(
            "classification_review_status"
        )
        extraction_review_status = cls.review_status_expr("extraction_review_status")
        return or_(
            classification_review_status == "dismissed",
            extraction_review_status == "dismissed",
        )

    @classmethod
    def needs_review_expr(cls):
        """Return files whose extraction summary explicitly still needs review."""
        extraction_review_status = cls.review_status_expr("extraction_review_status")
        extraction_needs_review = (
            func.coalesce(
                ContentItemEnrichmentState.extraction_summary_json[
                    "needs_review"
                ].astext,
                "false",
            )
            == "true"
        )
        return and_(
            cls.has_effective_extraction_expr(),
            extraction_review_status.is_(None),
            extraction_needs_review,
        )

    @classmethod
    def classification_missing_evidence_expr(cls):
        """Return classified files still missing classification evidence."""
        classification_review_status = cls.review_status_expr(
            "classification_review_status"
        )
        evidence_count = func.coalesce(
            func.jsonb_array_length(
                func.coalesce(
                    ContentItemEnrichmentState.classification_evidence_json,
                    cast(literal("[]"), JSONB),
                )
            ),
            0,
        )
        return and_(
            ExtractionFacetHelpers.effective_document_class_expr().is_not(None),
            classification_review_status.is_(None),
            evidence_count == 0,
        )

    @classmethod
    def extraction_missing_required_expr(cls):
        """Return extraction results missing required fields."""
        extraction_review_status = cls.review_status_expr("extraction_review_status")
        missing_required_count = func.coalesce(
            func.jsonb_array_length(
                ContentItemEnrichmentState.extraction_summary_json[
                    "missing_required_fields"
                ]
            ),
            0,
        )
        return and_(
            cls.has_effective_extraction_expr(),
            extraction_review_status.is_(None),
            missing_required_count > 0,
        )

    @classmethod
    def extraction_conflicted_fields_expr(cls):
        """Return extraction results with conflicted fields."""
        extraction_review_status = cls.review_status_expr("extraction_review_status")
        conflicted_fields_count = func.coalesce(
            func.jsonb_array_length(
                ContentItemEnrichmentState.extraction_summary_json["conflicted_fields"]
            ),
            0,
        )
        return and_(
            cls.has_effective_extraction_expr(),
            extraction_review_status.is_(None),
            conflicted_fields_count > 0,
        )

    @classmethod
    def extraction_missing_evidence_expr(cls):
        """Return extraction results with fewer evidence-backed fields than values."""
        extraction_review_status = cls.review_status_expr("extraction_review_status")
        fields_with_evidence = func.coalesce(
            cast(
                ContentItemEnrichmentState.extraction_summary_json[
                    "fields_with_evidence"
                ].astext,
                Integer,
            ),
            0,
        )
        effective_data = func.coalesce(
            ContentItemEnrichmentState.extraction_effective_data_json,
            cast(literal("{}"), JSONB),
        )
        effective_field_count = func.coalesce(
            cls.jsonb_object_key_count_expr(effective_data), 0
        )
        return and_(
            cls.has_effective_extraction_expr(),
            extraction_review_status.is_(None),
            effective_field_count > 0,
            fields_with_evidence < effective_field_count,
        )

    @classmethod
    def review_reason_expr(cls, review_reason: str):
        """Return one supported review-reason filter expression."""
        if review_reason == "missing_required_fields":
            return cls.extraction_missing_required_expr()
        if review_reason == "conflicted_fields":
            return cls.extraction_conflicted_fields_expr()
        if review_reason == "missing_evidence":
            return or_(
                cls.classification_missing_evidence_expr(),
                cls.extraction_missing_evidence_expr(),
            )
        raise ValueError(f"Unsupported review reason: {review_reason}")

    @classmethod
    def review_priority_expr(cls):
        """Return the review-priority sort expression by severity."""
        return case(
            (cls.extraction_missing_required_expr(), 0),
            (cls.extraction_conflicted_fields_expr(), 1),
            (
                or_(
                    cls.classification_missing_evidence_expr(),
                    cls.extraction_missing_evidence_expr(),
                ),
                2,
            ),
            (cls.unreviewed_enrichment_expr(), 3),
            (cls.corrected_enrichment_expr(), 4),
            (cls.accepted_enrichment_expr(), 5),
            else_=6,
        )

    @classmethod
    async def collect_review_reason_facets(
        cls,
        db: AsyncSession,
        stmt,
        *,
        review_reason_codes: tuple[str, ...],
    ) -> list[ReviewReasonFacet]:
        """Collect review-reason facet counts for the provided query."""
        facets: list[ReviewReasonFacet] = []
        for reason in review_reason_codes:
            count_stmt = select(func.count()).select_from(
                stmt.where(cls.review_reason_expr(reason)).subquery()
            )
            count = (await db.execute(count_stmt)).scalar() or 0
            if count:
                facets.append(ReviewReasonFacet(reason=reason, count=count))
        return facets

    @classmethod
    async def collect_review_summary(
        cls,
        db: AsyncSession,
        stmt,
        *,
        total: int,
        review_reason_codes: tuple[str, ...],
    ) -> ReviewQueueSummary:
        """Collect the review queue summary buckets for one filtered query."""

        async def _count_where(condition) -> int:
            count_stmt = select(func.count()).select_from(
                stmt.where(condition).subquery()
            )
            return (await db.execute(count_stmt)).scalar() or 0

        unreviewed = await _count_where(cls.unreviewed_enrichment_expr())
        accepted = await _count_where(cls.accepted_enrichment_expr())
        corrected = await _count_where(cls.corrected_enrichment_expr())
        dismissed = await _count_where(cls.dismissed_enrichment_expr())
        needs_review = await _count_where(cls.needs_review_expr())

        reason_counts: dict[str, int] = {}
        for reason in review_reason_codes:
            reason_counts[reason] = await _count_where(cls.review_reason_expr(reason))

        return ReviewQueueSummary(
            total=total,
            unreviewed=unreviewed,
            accepted=accepted,
            corrected=corrected,
            dismissed=dismissed,
            needs_review=needs_review,
            missing_required_fields=reason_counts.get("missing_required_fields", 0),
            conflicted_fields=reason_counts.get("conflicted_fields", 0),
            missing_evidence=reason_counts.get("missing_evidence", 0),
        )
