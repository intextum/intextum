"""Tests for folder-subtree scoping of flat content listing filters."""

from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.future import select

from models.sqlalchemy_models import IndexedContentItem
from services.content._stats.filters import (
    FlatContentListFilters,
    apply_flat_filters,
    scope_filters_to_path,
)


def _compiled_sql(filters: FlatContentListFilters) -> str:
    stmt = apply_flat_filters(
        select(IndexedContentItem),
        filters=filters,
        expressions=SimpleNamespace(),
    )
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_scope_filters_to_path_is_noop_without_path():
    filters = FlatContentListFilters()
    assert scope_filters_to_path(filters, None) is filters
    assert scope_filters_to_path(filters, "   ") is filters


def test_scope_filters_to_path_resolves_folder_and_prefix():
    folder = SimpleNamespace(uuid="folder-uuid", name="a")
    with patch(
        "services.content.helpers.resolve_db_context",
        return_value=(folder, "b/c/d"),
    ) as resolve:
        scoped = scope_filters_to_path(FlatContentListFilters(), "a/b/c/d")

    resolve.assert_called_once_with("a/b/c/d")
    assert scoped.path_folder_uuid == "folder-uuid"
    assert scoped.path_relative_prefix == "b/c/d"


def test_apply_flat_filters_limits_to_folder_subtree():
    sql = _compiled_sql(
        FlatContentListFilters(
            path_folder_uuid="folder-uuid",
            path_relative_prefix="b/c/d",
        )
    )
    assert "folder_uuid" in sql
    assert "'folder-uuid'" in sql
    # The folder root itself plus everything beneath it.
    assert "'b/c/d'" in sql
    assert "b/c/d/%" in sql


def test_apply_flat_filters_scopes_whole_folder_without_prefix():
    sql = _compiled_sql(FlatContentListFilters(path_folder_uuid="folder-uuid"))
    assert "'folder-uuid'" in sql
    # No relative-path constraint when scoping the entire folder.
    assert "LIKE" not in sql.upper()


def test_apply_flat_filters_unscoped_when_no_folder():
    sql = _compiled_sql(FlatContentListFilters())
    assert "folder_uuid =" not in sql
