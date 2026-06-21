"""Tests for the backend-managed permission system (PermissionService + UserService)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from models.user import User
from models.sqlalchemy_models import GroupExternalAlias
from services.group import DuplicateGroupAliasError, GroupService
from services.permission import PermissionService
from services.user import UserService, _recently_seen
from trustees import build_user_trustees


def _make_permission(folder_uuid, trustee, access="allow", granted_by=None):
    """Build a mock Permission object."""
    p = MagicMock()
    p.folder_uuid = folder_uuid
    p.trustee = trustee
    p.access = access
    p.granted_by = granted_by
    p.created_at = None
    return p


def _make_indexed_file(content_item_id, folder_uuid, allowed=None, denied=None):
    """Build a mock IndexedContentItem."""
    rec = MagicMock()
    rec.content_item_id = content_item_id
    rec.folder_uuid = folder_uuid
    rec.allowed_viewers = allowed
    rec.denied_viewers = denied
    return rec


class TestBuildUserTrustees:
    """Tests for the simplified build_user_trustees function."""

    def test_anonymous_user(self):
        result = build_user_trustees(None)
        assert result == ["everyone"]

    def test_authenticated_user(self):
        user = User(username="alice", sub="sub-alice", groups=["users"])
        result = build_user_trustees(user)
        assert result == ["everyone", "sub:sub-alice", "group:users"]
        # uid/gid/group trustees should NOT be present
        assert not any(t.startswith("uid:") for t in result)
        assert not any(t.startswith("gid:") for t in result)
        assert any(t.startswith("group:") for t in result)

    def test_username_lowercased(self):
        user = User(username="Alice", sub="Sub-Alice", groups=[])
        result = build_user_trustees(user)
        assert result == ["everyone", "sub:Sub-Alice"]

    def test_admin_user_includes_admin_marker(self):
        user = User(username="alice", sub="sub-alice", groups=["admins"], is_admin=True)
        result = build_user_trustees(user)
        assert "__acl_admin__" in result


class TestSplitPermissions:
    """Tests for PermissionService._split_permissions."""

    def test_allow_and_deny(self):
        perms = [
            _make_permission("f1", "everyone", "allow"),
            _make_permission("f1", "sub:sub-bob", "deny"),
        ]
        allowed, denied = PermissionService._split_permissions(perms)
        assert allowed == ["everyone"]
        assert denied == ["sub:sub-bob"]

    def test_all_allow(self):
        perms = [
            _make_permission("f1", "everyone", "allow"),
            _make_permission("f1", "sub:sub-alice", "allow"),
        ]
        allowed, denied = PermissionService._split_permissions(perms)
        assert allowed == ["everyone", "sub:sub-alice"]
        assert denied == []

    def test_empty(self):
        allowed, denied = PermissionService._split_permissions([])
        assert allowed == []
        assert denied == []


@pytest.mark.asyncio
class TestComputeEffectiveViewers:
    """Tests for compute_effective_viewers."""

    async def test_inherits_from_folder(self):
        """Folder permissions are returned."""
        db = AsyncMock()
        svc = PermissionService(db)

        folder_perm = _make_permission("folder1", "everyone", "allow")
        svc.get_permissions = AsyncMock(return_value=[folder_perm])

        allowed, denied = await svc.compute_effective_viewers("folder1")
        assert allowed == ["everyone"]

    async def test_no_permissions_returns_empty(self):
        """If no permissions set, returns empty lists."""
        db = AsyncMock()
        svc = PermissionService(db)
        svc.get_permissions = AsyncMock(return_value=[])

        allowed, denied = await svc.compute_effective_viewers("folder1")
        assert allowed == []
        assert denied == []


@pytest.mark.asyncio
class TestUserService:
    """Tests for UserService auto-provisioning."""

    async def test_ensure_user_inserts(self):
        """First login creates user record."""
        # Clear cache
        _recently_seen.clear()

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        db.execute.return_value = execute_result
        svc = UserService(db)
        user = User(
            username="newuser",
            sub="sub-newuser",
            email="new@example.com",
            groups=[],
        )

        await svc.ensure_user(user)
        assert db.execute.call_count == 2
        db.commit.assert_called_once()

    async def test_ensure_user_cache_skips_repeat(self):
        """Repeated calls within TTL skip DB write."""
        _recently_seen.clear()

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        db.execute.return_value = execute_result
        svc = UserService(db)
        user = User(
            username="cached", sub="sub-cached", email="c@example.com", groups=[]
        )

        # First call goes through
        await svc.ensure_user(user)
        assert db.execute.call_count == 2

        # Second call is cached
        await svc.ensure_user(user)
        assert (
            db.execute.call_count == 3
        )  # Only username check runs before cache short-circuit


class TestInMemoryAclChecks:
    """Verify in-memory ACL checks use the simplified trustee format."""

    def test_user_can_access_record_allowed(self):
        from services.content.helpers import user_can_access_record

        rec = _make_indexed_file("f1", "folder1", allowed=["everyone"])
        user = User(username="alice", sub="sub-alice", groups=["users"])

        assert user_can_access_record(rec, user) is True

    def test_user_can_access_record_denied(self):
        from services.content.helpers import user_can_access_record

        rec = _make_indexed_file(
            "f1",
            "folder1",
            allowed=["everyone"],
            denied=["sub:sub-alice"],
        )
        user = User(username="alice", sub="sub-alice", groups=["users"])

        assert user_can_access_record(rec, user) is False

    def test_user_can_access_record_no_acl_info_denies(self):
        from services.content.helpers import user_can_access_record

        rec = _make_indexed_file("f1", "folder1", allowed=None, denied=None)
        user = User(username="alice", sub="sub-alice", groups=["users"])

        assert user_can_access_record(rec, user) is False

    def test_admin_bypass(self):
        from services.content.helpers import user_can_access_record

        rec = _make_indexed_file("f1", "folder1", allowed=None, denied=None)
        admin = User(
            username="admin", sub="sub-admin", groups=["admins"], is_admin=True
        )

        assert user_can_access_record(rec, admin) is True

    def test_missing_acl_info_fails_closed_without_runtime_bypass(self):
        from services.content.helpers import user_can_access_record

        rec = _make_indexed_file("f1", "folder1", allowed=None, denied=None)
        user = User(username="alice", sub="sub-alice", groups=["users"])

        assert user_can_access_record(rec, user) is False


@pytest.mark.asyncio
class TestGroupService:
    async def test_replace_proxy_aliases_dedupes_normalized_values(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None
        db.execute.return_value = empty_result
        svc = GroupService(db)

        await svc.replace_proxy_aliases(
            "admins",
            ["Admins", " admins ", "Operations"],
        )

        assert db.add.call_count == 2
        added_aliases = [call.args[0].external_value for call in db.add.call_args_list]
        assert added_aliases == ["admins", "operations"]
        db.commit.assert_awaited_once()

    async def test_replace_proxy_aliases_raises_for_alias_owned_by_another_group(self):
        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        conflict = GroupExternalAlias(
            group_slug="other",
            provider="proxy",
            external_value="admins",
        )
        conflict_result = MagicMock()
        conflict_result.scalar_one_or_none.return_value = conflict
        db.execute.return_value = conflict_result
        svc = GroupService(db)

        with pytest.raises(DuplicateGroupAliasError):
            await svc.replace_proxy_aliases("admins", ["Admins"])

        db.add.assert_not_called()
        db.commit.assert_not_called()
