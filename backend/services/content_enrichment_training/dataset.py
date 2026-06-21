"""Dataset assembly for content-enrichment training tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.content.enrichment_training import (
    ContentEnrichmentTrainingExample,
    ContentEnrichmentWorkerTrainingDataset,
)
from models.sqlalchemy_models import (
    ContentChunk,
    ContentItemEnrichmentState,
    IndexedContentItem,
    TaskQueue,
)
from services.task_queue.access_ops import task_metadata_payload

_REVIEWED_STATUSES = ("accepted", "corrected")
_CLASSIFICATION_TRAINING_MAX_CHARS = 8_000


@dataclass(frozen=True)
class ChunkRecord:
    """One stored chunk with the context the inference path also uses."""

    text: str
    headings: list[str] = field(default_factory=list)


def _compact_blank_lines(text: str) -> str:
    """Collapse runs of 3+ blank lines but keep single blank-line paragraph breaks."""
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip():
            cleaned.append(line)
            blank_run = 0
        else:
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned)


def normalize_training_input(text: str, *, max_chars: int) -> str:
    """Cap a contextualized training input while preserving paragraph structure."""
    compacted = _compact_blank_lines(text)
    if max_chars <= 0 or len(compacted) <= max_chars:
        return compacted
    return compacted[:max_chars].rstrip()


def _contextualize_chunk(record: ChunkRecord) -> str:
    """Render one chunk like the worker's extraction window: heading path then body."""
    body = record.text.strip()
    headings = _clean_headings(record.headings)
    if not body and not headings:
        return ""
    if headings:
        prefix = "\n".join(headings)
        return f"{prefix}\n\n{body}" if body else prefix
    return body


def _clean_headings(values: Any) -> list[str]:
    return [
        heading.strip()
        for heading in values or []
        if isinstance(heading, str) and heading.strip()
    ]


def document_text_from_chunk_records(
    chunks: list[ChunkRecord], *, max_chars: int
) -> str:
    """Concatenate contextualized chunks for training, matching the inference shape."""
    parts = [
        contextualized
        for chunk in chunks
        if (contextualized := _contextualize_chunk(chunk))
    ]
    return normalize_training_input("\n\n".join(parts), max_chars=max_chars)


class ContentEnrichmentTrainingDatasetBuilder:
    """Build worker datasets from reviewed enrichment records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def reviewed_example_count(self) -> int:
        stmt = (
            select(func.count())
            .select_from(ContentItemEnrichmentState)
            .where(
                ContentItemEnrichmentState.classification_review_status.in_(
                    _REVIEWED_STATUSES
                )
            )
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def reviewed_training_records(self) -> list[IndexedContentItem]:
        stmt = select(IndexedContentItem).order_by(
            IndexedContentItem.updated_at.desc(), IndexedContentItem.content_item_id
        )
        stmt = stmt.join(ContentItemEnrichmentState)
        stmt = stmt.where(
            ContentItemEnrichmentState.classification_review_status.in_(
                _REVIEWED_STATUSES
            )
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def chunk_records_by_file_id(
        self, file_ids: list[str]
    ) -> dict[str, list[ChunkRecord]]:
        if not file_ids:
            return {}

        result = await self.db.execute(
            select(
                ContentChunk.content_item_id,
                ContentChunk.text,
                ContentChunk.headings,
            )
            .where(ContentChunk.content_item_id.in_(file_ids))
            .order_by(ContentChunk.content_item_id, ContentChunk.chunk_index)
        )
        grouped: dict[str, list[ChunkRecord]] = {}
        for content_item_id, text, headings in result.all():
            if not isinstance(content_item_id, str) or not isinstance(text, str):
                continue
            grouped.setdefault(content_item_id, []).append(
                ChunkRecord(text=text, headings=_clean_headings(headings))
            )
        return grouped

    @staticmethod
    def classification_example(
        record: IndexedContentItem,
        *,
        chunks: list[ChunkRecord],
        config_snapshot: dict[str, Any] | None,
    ) -> ContentEnrichmentTrainingExample | None:
        state = record.enrichment_state
        if state is None:
            return None
        review_status = state.classification_review_status
        if review_status not in _REVIEWED_STATUSES:
            return None
        true_label = state.classification_effective_label
        if not isinstance(true_label, str) or not true_label.strip():
            return None

        labels: list[str] = []
        for item in (config_snapshot or {}).get("document_classification_labels", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                labels.append(name)
        if not labels:
            return None

        normalized_input = document_text_from_chunk_records(
            chunks,
            max_chars=_CLASSIFICATION_TRAINING_MAX_CHARS,
        )
        if not normalized_input:
            return None

        reviewed_at = (
            state.classification_reviewed_at.isoformat()
            if state.classification_reviewed_at
            else None
        )
        reviewed_by = state.classification_reviewed_by
        return ContentEnrichmentTrainingExample(
            content_item_id=record.content_item_id,
            relative_path=record.relative_path,
            input=normalized_input,
            output={
                "classifications": [
                    {
                        "task": "document_class",
                        "labels": labels,
                        "true_label": true_label.strip(),
                    }
                ]
            },
            review_status=review_status,
            reviewed_at=reviewed_at,
            reviewed_by=reviewed_by,
        )

    async def build_worker_training_dataset(
        self, task: TaskQueue
    ) -> ContentEnrichmentWorkerTrainingDataset | None:
        metadata = task_metadata_payload(task, include_content_item_id=False)
        config_snapshot = (
            metadata.get("config_snapshot")
            if isinstance(metadata.get("config_snapshot"), dict)
            else None
        )

        records = await self.reviewed_training_records()
        chunks_by_file_id = await self.chunk_records_by_file_id(
            [record.content_item_id for record in records]
        )

        examples: list[ContentEnrichmentTrainingExample] = []
        for record in records:
            chunks = chunks_by_file_id.get(record.content_item_id, [])
            example = self.classification_example(
                record,
                chunks=chunks,
                config_snapshot=config_snapshot,
            )
            if example is not None:
                examples.append(example)

        return ContentEnrichmentWorkerTrainingDataset(
            task_id=task.id,
            training_job_id=str(metadata.get("training_job_id") or ""),
            registry_model_id=str(metadata.get("registry_model_id") or ""),
            target_kind="classification",
            training_method=str(metadata.get("training_method") or "lora"),
            base_model=str(metadata.get("base_model") or ""),
            target_name=None,
            config_fingerprint=str(metadata.get("config_fingerprint") or ""),
            config_snapshot=config_snapshot,
            examples=examples,
        )
