"""Validation helpers for embedding vector dimensions."""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import text

from models.sqlalchemy_models import ContentChunk

_VECTOR_TYPE_RE = re.compile(r"^vector\((\d+)\)$", re.IGNORECASE)


class VectorDimensionConfigurationError(RuntimeError):
    """Raised when configured embedding dimensions do not match storage."""


class VectorDimensionMismatchError(ValueError):
    """Raised when one vector payload has the wrong number of dimensions."""


def declared_vector_column_dimension() -> int:
    """Return the SQLAlchemy-declared dimension for content chunk embeddings."""
    dimension = getattr(ContentChunk.__table__.c.embedding.type, "dim", None)
    if not isinstance(dimension, int) or dimension <= 0:
        raise VectorDimensionConfigurationError(
            "content_chunks.embedding must declare a fixed pgvector dimension"
        )
    return dimension


def configured_embedding_vector_size(settings: object) -> int:
    """Return the configured embedding dimension, falling back to schema default."""
    default = declared_vector_column_dimension()
    raw_value = getattr(settings, "EMBEDDING_VECTOR_SIZE", default)
    if not isinstance(raw_value, int | float | str):
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise VectorDimensionConfigurationError(
            "EMBEDDING_VECTOR_SIZE must be a positive integer"
        ) from exc
    if value <= 0:
        raise VectorDimensionConfigurationError(
            "EMBEDDING_VECTOR_SIZE must be a positive integer"
        )
    return value


def validate_configured_vector_dimension(settings: object) -> int:
    """Ensure configured embedding dimensions match the declared vector column."""
    configured = configured_embedding_vector_size(settings)
    declared = declared_vector_column_dimension()
    if configured != declared:
        raise VectorDimensionConfigurationError(
            "EMBEDDING_VECTOR_SIZE="
            f"{configured} does not match content_chunks.embedding vector({declared})"
        )
    return configured


def _parse_vector_type_dimension(type_name: str) -> int | None:
    match = _VECTOR_TYPE_RE.match(type_name.strip())
    if match is None:
        return None
    return int(match.group(1))


async def validate_database_vector_dimensions(conn, settings: object) -> int:
    """Ensure runtime config, SQLAlchemy metadata, and the DB vector column agree."""
    configured = validate_configured_vector_dimension(settings)
    result = await conn.execute(
        text(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.oid = to_regclass('content_chunks')
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
            """
        )
    )
    type_name = result.scalar_one_or_none()
    if not isinstance(type_name, str):
        raise VectorDimensionConfigurationError(
            "content_chunks.embedding is missing; run database migrations"
        )

    database_dimension = _parse_vector_type_dimension(type_name)
    if database_dimension is None:
        raise VectorDimensionConfigurationError(
            "content_chunks.embedding must be a fixed-dimension pgvector column"
        )
    if database_dimension != configured:
        raise VectorDimensionConfigurationError(
            "EMBEDDING_VECTOR_SIZE="
            f"{configured} does not match database content_chunks.embedding "
            f"vector({database_dimension})"
        )
    return configured


def validate_embedding_vector_length(
    vector: Sequence[float],
    settings: object,
    *,
    context: str,
) -> None:
    """Ensure one embedding vector has the configured number of dimensions."""
    expected = validate_configured_vector_dimension(settings)
    actual = len(vector)
    if actual != expected:
        raise VectorDimensionMismatchError(
            f"{context} has {actual} dimensions; expected {expected}"
        )


def validate_embedding_vectors_length(
    vectors: Sequence[Sequence[float]],
    settings: object,
    *,
    context: str,
) -> None:
    """Ensure every embedding vector has the configured number of dimensions."""
    for index, vector in enumerate(vectors):
        validate_embedding_vector_length(
            vector,
            settings,
            context=f"{context}[{index}]",
        )
