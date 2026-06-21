"""Tests for embedding vector dimension validation."""

from types import SimpleNamespace

import pytest

from services.vector_dimensions import (
    VectorDimensionConfigurationError,
    VectorDimensionMismatchError,
    declared_vector_column_dimension,
    validate_configured_vector_dimension,
    validate_database_vector_dimensions,
    validate_embedding_vector_length,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Connection:
    def __init__(self, value):
        self.value = value

    async def execute(self, _stmt):
        return _ScalarResult(self.value)


def test_configured_vector_dimension_matches_declared_schema():
    assert (
        validate_configured_vector_dimension(
            SimpleNamespace(EMBEDDING_VECTOR_SIZE=1024)
        )
        == 1024
    )


def test_configured_vector_dimension_rejects_schema_drift():
    with pytest.raises(VectorDimensionConfigurationError) as exc_info:
        validate_configured_vector_dimension(SimpleNamespace(EMBEDDING_VECTOR_SIZE=768))

    assert "EMBEDDING_VECTOR_SIZE=768" in str(exc_info.value)
    assert "content_chunks.embedding vector(1024)" in str(exc_info.value)


@pytest.mark.asyncio
async def test_database_vector_dimension_rejects_column_drift():
    with pytest.raises(VectorDimensionConfigurationError) as exc_info:
        await validate_database_vector_dimensions(
            _Connection("vector(768)"),
            SimpleNamespace(EMBEDDING_VECTOR_SIZE=declared_vector_column_dimension()),
        )

    assert "database content_chunks.embedding vector(768)" in str(exc_info.value)


def test_embedding_vector_length_rejects_wrong_payload_dimension():
    with pytest.raises(VectorDimensionMismatchError) as exc_info:
        validate_embedding_vector_length(
            [0.1, 0.2],
            SimpleNamespace(EMBEDDING_VECTOR_SIZE=1024),
            context="query_vector",
        )

    assert str(exc_info.value) == "query_vector has 2 dimensions; expected 1024"
