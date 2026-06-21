"""Tests for trustee normalization helpers."""

import pytest
from fastapi import HTTPException

from routers.permissions import _normalize_trustee


def test_normalize_trustee_accepts_sub_identifier():
    assert _normalize_trustee("sub:abc-123") == "sub:abc-123"


def test_normalize_trustee_accepts_everyone_case_insensitively():
    assert _normalize_trustee("Everyone") == "everyone"


def test_normalize_trustee_rejects_removed_user_identifier():
    with pytest.raises(
        HTTPException,
        match="trustee must be 'everyone', 'sub:<id>', or 'group:<slug>'",
    ):
        _normalize_trustee("user:alice")
