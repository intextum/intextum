"""Tests for content item invariant helpers."""

import pytest

from models.content.items import ContentItemKind
from models.sqlalchemy_models import IndexedContentItem
from services.content.invariants import (
    ContentItemInvariantInput,
    normalize_content_item_kind,
    normalize_content_relative_path,
    safe_content_item_kind,
    validate_content_item_invariants,
    validate_non_negative_size,
)


def test_normalize_content_item_kind_accepts_supported_kinds():
    assert normalize_content_item_kind("file") == "file"
    assert normalize_content_item_kind(ContentItemKind.EMAIL_MESSAGE) == "email_message"


def test_normalize_content_item_kind_rejects_unsupported_kinds():
    with pytest.raises(ValueError, match="Unsupported content item kind"):
        normalize_content_item_kind("document")


def test_safe_content_item_kind_defaults_malformed_rows_to_file():
    assert safe_content_item_kind("missing") == ContentItemKind.FILE
    assert safe_content_item_kind(None) == ContentItemKind.FILE


@pytest.mark.parametrize("path", ["/absolute.pdf", "../escape.pdf", "a/../b.pdf"])
def test_normalize_content_relative_path_rejects_absolute_or_traversal(path):
    with pytest.raises(ValueError):
        normalize_content_relative_path(path)


def test_normalize_content_relative_path_rejects_empty_file_paths():
    with pytest.raises(ValueError, match="relative_path is required"):
        normalize_content_relative_path("")


def test_validate_non_negative_size_rejects_negative_values():
    with pytest.raises(ValueError, match="size_bytes must be non-negative"):
        validate_non_negative_size(-1)


def test_folder_invariants_require_directory_container_shape():
    assert (
        validate_content_item_invariants(
            ContentItemInvariantInput(
                content_kind="folder",
                relative_path="",
                size_bytes=0,
                is_dir=True,
                is_container=True,
            ),
            allow_empty_path=True,
        )
        == "folder"
    )

    with pytest.raises(ValueError, match="folder content items"):
        validate_content_item_invariants(
            ContentItemInvariantInput(
                content_kind="folder",
                relative_path="folder",
                size_bytes=0,
                is_dir=False,
                is_container=True,
            )
        )


def test_email_invariants_require_email_details():
    with pytest.raises(ValueError, match="require email details"):
        validate_content_item_invariants(
            ContentItemInvariantInput(
                content_kind="email_message",
                relative_path="mail/message.eml",
                size_bytes=1,
                is_dir=False,
                is_container=False,
            )
        )


def test_attachment_invariants_require_linkage_and_details():
    with pytest.raises(ValueError, match="require attachment details"):
        validate_content_item_invariants(
            ContentItemInvariantInput(
                content_kind="attachment",
                relative_path="mail/attachment.pdf",
                size_bytes=1,
                is_dir=False,
                is_container=False,
                parent_content_item_id="mail-1",
                container_content_item_id="mail-1",
                email_message_content_item_id="mail-1",
            )
        )

    with pytest.raises(ValueError, match="require email parent linkage"):
        validate_content_item_invariants(
            ContentItemInvariantInput(
                content_kind="attachment",
                relative_path="mail/attachment.pdf",
                size_bytes=1,
                is_dir=False,
                is_container=False,
                has_attachment_details=True,
            )
        )


def test_indexed_content_item_model_declares_hardening_constraints():
    constraint_names = {
        constraint.name for constraint in IndexedContentItem.__table__.constraints
    }
    index_names = {index.name for index in IndexedContentItem.__table__.indexes}

    assert "ck_indexed_content_items_content_kind" in constraint_names
    assert "ck_indexed_content_items_size_non_negative" in constraint_names
    assert "ck_indexed_content_items_kind_directory_consistency" in constraint_names
    assert "ux_indexed_content_items_external_id" in index_names
