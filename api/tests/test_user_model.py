"""Tests for User model."""

from models.user import User


class TestUser:
    """Tests for User dataclass."""

    def test_display_name_prefers_preferred_username(self):
        """display_name returns preferred_username when available."""
        user = User(
            username="jdoe",
            preferred_username="John Doe",
        )
        assert user.display_name == "John Doe"

    def test_display_name_falls_back_to_username(self):
        """display_name returns username when preferred_username not set."""
        user = User(username="jdoe")
        assert user.display_name == "jdoe"

    def test_normalized_sub_strips_value(self):
        """normalized_sub strips surrounding whitespace."""
        user = User(username="jdoe", sub="  sub-123  ")
        assert user.normalized_sub == "sub-123"

    def test_normalized_sub_returns_none_when_missing(self):
        """normalized_sub returns None for missing or blank values."""
        assert User(username="jdoe").normalized_sub is None
        assert User(username="jdoe", sub="   ").normalized_sub is None

    def test_require_stable_sub_raises_when_missing(self):
        """require_stable_sub raises when no stable subject identifier exists."""
        user = User(username="jdoe")

        try:
            user.require_stable_sub()
        except ValueError as exc:
            assert "stable subject identifier" in str(exc)
        else:
            raise AssertionError("Expected require_stable_sub to raise ValueError")

    def test_is_in_group_case_insensitive(self):
        """is_in_group is case-insensitive."""
        user = User(username="test", groups=["Admins", "Users"])

        assert user.is_in_group("admins") is True
        assert user.is_in_group("ADMINS") is True
        assert user.is_in_group("Admins") is True
        assert user.is_in_group("developers") is False

    def test_is_in_any_group(self):
        """is_in_any_group checks multiple groups."""
        user = User(username="test", groups=["users", "developers"])

        assert user.is_in_any_group(["admins", "users"]) is True
        assert user.is_in_any_group(["admins", "managers"]) is False
        assert user.is_in_any_group([]) is False

    def test_str_representation(self):
        """String representation includes username and groups."""
        user = User(username="test", groups=["a", "b"])
        assert "test" in str(user)
        assert "a" in str(user)

    def test_default_values(self):
        """Default values are set correctly."""
        user = User(username="test")
        assert user.email is None
        assert user.groups == []
        assert user.preferred_username is None
        assert user.uid is None
        assert user.gids == []
