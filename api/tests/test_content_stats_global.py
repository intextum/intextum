"""Focused tests for global file stats helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import false

from services.content._stats.global_stats import GlobalContentStatsCollector


def _fetchone_result(count: int, total_size: int):
    result = MagicMock()
    result.fetchone.return_value = (count, total_size)
    return result


def _scalar_result(value: int):
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest.mark.asyncio
async def test_global_stats_collector_collects_all_counts():
    """Global stats helper should collect each aggregate query."""
    service = MagicMock()
    service.db = MagicMock()
    service.db.execute = AsyncMock(
        side_effect=[
            _fetchone_result(12, 4096),
            _scalar_result(3),
            _scalar_result(5),
        ]
    )
    service._stale_enrichment_expr.return_value = false()

    result = await GlobalContentStatsCollector(
        service=service,
        effective_settings=SimpleNamespace(
            document_classification_enabled=True,
            document_extraction_enabled=True,
            document_extraction_model="registry:global-extract",
            document_extraction_llm_model="registry:llm-extract",
            document_extraction_schema_models={"permit_core": "registry:permit-v2"},
            document_extraction_schemas=[
                SimpleNamespace(name="permit_core", fields=[]),
            ],
        ),
        classification_fingerprint="class-fingerprint",
        extraction_fingerprint="extract-fingerprint",
    ).collect()

    assert result == {
        "total_items": 12,
        "total_size_bytes": 4096,
        "processing_count": 3,
        "stale_enrichment_count": 5,
    }
    stale_stmt = service.db.execute.await_args_list[2].args[0]
    assert "JOIN content_item_enrichment_states" in str(stale_stmt)
    service._stale_enrichment_expr.assert_called_once_with(
        classification_enabled=True,
        extraction_enabled=True,
        classification_fingerprint="class-fingerprint",
        extraction_fingerprint="extract-fingerprint",
        extraction_model="registry:global-extract",
        extraction_schema_models={"permit_core": "registry:permit-v2"},
    )
