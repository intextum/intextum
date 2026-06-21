"""Tests for request-scoped chat context resolution."""

from chat.context import build_context_scope, resolve_get_document_target_path
from models.connector_types import LocalFsDataConnector
from services.connector import connector_registry
from services.utils import compute_content_item_id


def test_build_context_scope_resolves_file_ids_and_deduplicates(runtime_sources):
    """Selected context paths should resolve once into canonical scope metadata."""
    _ = runtime_sources

    scope = build_context_scope(
        [
            " documents/file1.pdf ",
            "/documents/file1.pdf/",
            "images/image1.jpg",
            "unknown/path.txt",
        ]
    )

    assert scope.has_selection is True
    assert scope.has_constraints is True
    assert scope.constraints == [
        ("documents/file1.pdf", "folder-documents", "file1.pdf"),
        ("images/image1.jpg", "folder-images", "image1.jpg"),
    ]
    assert scope.file_ids == [
        compute_content_item_id("folder-documents", "file1.pdf"),
        compute_content_item_id("folder-images", "image1.jpg"),
    ]
    assert scope.contains("folder-documents", "file1.pdf") is True
    assert scope.contains("folder-images", "image1.jpg") is True
    assert scope.contains("folder-documents", "missing.pdf") is False


def test_build_context_scope_ignores_non_browsable_system_connectors():
    """Chat context should not expose hidden runtime connectors as selectable roots."""
    connector_registry.set_connectors(
        [
            LocalFsDataConnector(
                uuid="system:archive",
                name="System Archive",
                path="/tmp/archive",
                browsable=False,
                system_managed=True,
            )
        ]
    )

    scope = build_context_scope(["System Archive/private.pdf"])

    assert scope.has_selection is True
    assert scope.has_constraints is False


def test_resolve_get_document_target_path_matches_single_context_candidate(
    runtime_sources,
):
    """Bare filenames should resolve against one matching scoped file path."""
    _ = runtime_sources
    scope = build_context_scope(["documents/file1.pdf"])

    resolved_path, error = resolve_get_document_target_path(
        raw_file_path="file1.pdf",
        context_scope=scope,
        source_paths=[],
    )

    assert error is None
    assert resolved_path == "documents/file1.pdf"


def test_resolve_get_document_target_path_reports_ambiguity(runtime_sources):
    """Ambiguous filenames should return a helpful disambiguation message."""
    _ = runtime_sources
    scope = build_context_scope(["documents/report.pdf", "images/report.pdf"])

    resolved_path, error = resolve_get_document_target_path(
        raw_file_path="report.pdf",
        context_scope=scope,
        source_paths=[],
    )

    assert resolved_path is None
    assert error is not None
    assert "Ambiguous document path" in error
