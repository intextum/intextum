"""Tests for auth dependencies using request-scoped current user state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from starlette.responses import Response as StarletteResponse

from models.sqlalchemy_models import AppUser, UserIdentity
from models.user import User
from services.auth import LoginThrottleState
from services.password_policy import PasswordPolicyError, validate_local_password
from services.user import DuplicateUsernameError, UserService


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.decode("latin-1").lower() == "set-cookie"
    ]


class FakeValkey:
    def __init__(self):
        self.values: dict[str, str | int] = {}
        self.ttls: dict[str, int] = {}

    async def exists(self, *keys):
        return sum(1 for key in keys if key in self.values)

    async def incr(self, key):
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    async def expire(self, key, seconds):
        self.ttls[key] = seconds

    async def set(self, key, value, ex=None):
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex

    async def get(self, key):
        return self.values.get(key)

    async def ttl(self, key):
        return self.ttls.get(key, -1)

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.ttls.pop(key, None)


class TestGetCurrentUser:
    def test_returns_none_when_request_state_has_no_user(self):
        from auth.dependencies import get_current_user

        request = MagicMock()
        request.state.current_user = None

        assert get_current_user(request) is None

    def test_returns_request_scoped_current_user(self):
        from auth.dependencies import get_current_user

        request = MagicMock()
        request.state.current_user = User(username="alice", sub="sub-alice")

        user = get_current_user(request)

        assert user is not None
        assert user.username == "alice"
        assert user.sub == "sub-alice"


class TestRequireUser:
    def test_returns_user_when_authenticated(self):
        from auth.dependencies import require_user

        request = MagicMock()
        request.state.current_user = User(username="alice", sub="sub-alice")

        user = require_user(request)

        assert user.username == "alice"

    def test_raises_401_when_not_authenticated(self):
        from auth.dependencies import require_user

        request = MagicMock()
        request.state.current_user = None

        with pytest.raises(HTTPException) as exc_info:
            require_user(request)

        assert exc_info.value.status_code == 401

    def test_raises_401_for_disabled_user(self):
        from auth.dependencies import require_user

        request = MagicMock()
        request.state.current_user = User(
            username="alice",
            sub="sub-alice",
            is_disabled=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            require_user(request)

        assert exc_info.value.status_code == 401


class TestRequireAdmin:
    def test_returns_user_when_admin(self):
        from auth.dependencies import require_admin

        request = MagicMock()
        request.state.current_user = User(
            username="admin",
            sub="sub-admin",
            is_admin=True,
        )

        user = require_admin(request)

        assert user.username == "admin"

    def test_raises_403_when_not_admin(self):
        from auth.dependencies import require_admin

        request = MagicMock()
        request.state.current_user = User(
            username="alice",
            sub="sub-alice",
            is_admin=False,
        )

        with pytest.raises(HTTPException) as exc_info:
            require_admin(request)

        assert exc_info.value.status_code == 403

    def test_raises_401_when_not_authenticated(self):
        from auth.dependencies import require_admin

        request = MagicMock()
        request.state.current_user = None

        with pytest.raises(HTTPException) as exc_info:
            require_admin(request)

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
class TestMustChangePasswordMiddleware:
    async def test_blocks_normal_access_for_local_user_who_must_change_password(self):
        from main import auth_context_middleware

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/content/tree"
        request.cookies = {}
        request.headers = {}
        user = User(
            username="alice",
            sub="app:alice",
            auth_provider="local",
            must_change_password=True,
        )

        async def call_next(_request):
            return StarletteResponse("ok")

        with patch("main.resolve_request_user", new=AsyncMock(return_value=user)):
            response = await auth_context_middleware(request, call_next)

        assert response.status_code == 403

    async def test_allows_me_for_local_user_who_must_change_password(self):
        from main import auth_context_middleware

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/me"
        request.cookies = {}
        request.headers = {}
        user = User(
            username="alice",
            sub="app:alice",
            auth_provider="local",
            must_change_password=True,
        )

        async def call_next(_request):
            return StarletteResponse("ok")

        with patch("main.resolve_request_user", new=AsyncMock(return_value=user)):
            response = await auth_context_middleware(request, call_next)

        assert response.status_code == 200


@pytest.mark.asyncio
async def test_local_session_service_drops_invalid_session_payload():
    from services.auth.session import LocalSessionService

    valkey = FakeValkey()
    key = LocalSessionService._key("session-1")
    valkey.values[key] = "{not-json"

    with patch("services.auth.session.get_valkey_client", return_value=valkey):
        session = await LocalSessionService().get_session("session-1")

    assert session is None
    assert key not in valkey.values


@pytest.mark.asyncio
class TestChangePassword:
    async def test_reissues_local_session_cookies_after_password_change(self):
        from routers.auth import change_password
        from routers.auth import ChangePasswordRequest

        settings = SimpleNamespace(
            AUTH_LOCAL_ENABLED=True,
            AUTH_SESSION_COOKIE_NAME="intextum_session",
            AUTH_SESSION_ABSOLUTE_TTL_SECONDS=604800,
            AUTH_SESSION_SECURE_COOKIE=False,
            AUTH_CSRF_COOKIE_NAME="intextum_csrf",
        )
        app_user = SimpleNamespace(sub="app:user", session_version=2)
        session = SimpleNamespace(
            session_id="new-session",
            csrf_token="new-csrf",
        )
        svc = MagicMock()
        svc.change_password = AsyncMock(return_value=True)
        svc.get_user_by_sub = AsyncMock(return_value=app_user)
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(return_value=session)
        response = Response()

        with (
            patch("config.get_settings", return_value=settings),
            patch("routers.auth.UserService", return_value=svc),
            patch("routers.auth.LocalSessionService", return_value=session_svc),
        ):
            result = await change_password(
                body=ChangePasswordRequest(
                    current_password="old-password",
                    new_password="new-password",
                ),
                response=response,
                user=User(username="alice", sub="app:user", auth_provider="local"),
                db=AsyncMock(),
            )

        assert result == {"updated": True}
        session_svc.create_session.assert_awaited_once_with(
            user_sub="app:user",
            session_version=2,
            auth_provider="local",
        )
        cookies = _set_cookie_headers(response)
        assert any("intextum_session=new-session" in cookie for cookie in cookies)
        assert any("intextum_csrf=new-csrf" in cookie for cookie in cookies)

    async def test_rejects_weak_new_password(self):
        from routers.auth import ChangePasswordRequest
        from routers.auth import change_password

        svc = MagicMock()
        svc.change_password = AsyncMock(
            side_effect=PasswordPolicyError("Password is too common")
        )

        with patch("routers.auth.UserService", return_value=svc):
            with pytest.raises(HTTPException) as exc_info:
                await change_password(
                    body=ChangePasswordRequest(
                        current_password="current-password",
                        new_password="password123",
                    ),
                    response=Response(),
                    user=User(username="alice", sub="app:user", auth_provider="local"),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Password is too common"


@pytest.mark.asyncio
class TestLocalLoginThrottle:
    async def test_returns_429_when_failed_attempt_locks_identifier_or_ip(self):
        from routers.auth import LocalLoginRequest
        from routers.auth import login_local

        settings = SimpleNamespace(AUTH_LOCAL_ENABLED=True)
        svc = MagicMock()
        svc.authenticate_local = AsyncMock(return_value=None)
        throttle = MagicMock()
        throttle.check_allowed = AsyncMock(
            return_value=LoginThrottleState(allowed=True)
        )
        throttle.record_failure = AsyncMock(
            return_value=LoginThrottleState(
                allowed=False,
                retry_after_seconds=42,
            )
        )
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

        with (
            patch("config.get_settings", return_value=settings),
            patch("routers.auth.UserService", return_value=svc),
            patch("routers.auth.LocalLoginThrottle", return_value=throttle),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await login_local(
                    body=LocalLoginRequest(
                        username_or_email="alice",
                        password="wrong",
                    ),
                    request=request,
                    response=Response(),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers == {"Retry-After": "42"}
        throttle.record_failure.assert_awaited_once_with(
            identifier="alice",
            client_ip="127.0.0.1",
        )

    async def test_clears_throttle_after_successful_login(self):
        from routers.auth import LocalLoginRequest
        from routers.auth import login_local

        settings = SimpleNamespace(
            AUTH_LOCAL_ENABLED=True,
            AUTH_SESSION_COOKIE_NAME="intextum_session",
            AUTH_SESSION_ABSOLUTE_TTL_SECONDS=604800,
            AUTH_SESSION_SECURE_COOKIE=False,
            AUTH_CSRF_COOKIE_NAME="intextum_csrf",
        )
        user = User(username="alice", sub="app:alice", auth_provider="local")
        app_user = SimpleNamespace(sub="app:alice", session_version=3)
        svc = MagicMock()
        svc.authenticate_local = AsyncMock(return_value=user)
        svc.get_user_by_sub = AsyncMock(return_value=app_user)
        throttle = MagicMock()
        throttle.check_allowed = AsyncMock(
            return_value=LoginThrottleState(allowed=True)
        )
        throttle.clear = AsyncMock()
        session_svc = MagicMock()
        session_svc.create_session = AsyncMock(
            return_value=SimpleNamespace(session_id="sid", csrf_token="csrf")
        )
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

        with (
            patch("config.get_settings", return_value=settings),
            patch("routers.auth.UserService", return_value=svc),
            patch("routers.auth.LocalLoginThrottle", return_value=throttle),
            patch("routers.auth.LocalSessionService", return_value=session_svc),
        ):
            result = await login_local(
                body=LocalLoginRequest(
                    username_or_email=" alice ",
                    password="correct-password",
                ),
                request=request,
                response=Response(),
                db=AsyncMock(),
            )

        assert result["sub"] == "app:alice"
        throttle.clear.assert_awaited_once_with(
            identifier="alice",
            client_ip="127.0.0.1",
        )

    async def test_valkey_throttle_locks_and_clears_username_and_ip(self):
        from services.auth import LocalLoginThrottle

        fake_valkey = FakeValkey()
        settings = SimpleNamespace(
            AUTH_LOGIN_THROTTLE_ENABLED=True,
            AUTH_LOGIN_MAX_ATTEMPTS=2,
            AUTH_LOGIN_WINDOW_SECONDS=60,
            AUTH_LOGIN_LOCKOUT_SECONDS=300,
        )
        with (
            patch("services.auth.throttle.get_settings", return_value=settings),
            patch("services.auth.throttle.get_valkey_client", return_value=fake_valkey),
        ):
            throttle = LocalLoginThrottle()
            first = await throttle.record_failure(
                identifier="Alice",
                client_ip="127.0.0.1",
            )
            second = await throttle.record_failure(
                identifier="alice",
                client_ip="127.0.0.1",
            )
            blocked = await throttle.check_allowed(
                identifier="alice",
                client_ip="127.0.0.1",
            )
            await throttle.clear(identifier="alice", client_ip="127.0.0.1")
            allowed = await throttle.check_allowed(
                identifier="alice",
                client_ip="127.0.0.1",
            )

        assert first.allowed is True
        assert second.allowed is False
        assert second.retry_after_seconds == 300
        assert blocked.allowed is False
        assert allowed.allowed is True


@pytest.mark.asyncio
class TestAdminUserRoutes:
    async def test_create_user_returns_409_for_duplicate_username(self):
        from routers.admin.common import CreateUserRequest
        from routers.admin.users import create_user

        svc = MagicMock()
        svc.create_local_user = AsyncMock(
            side_effect=DuplicateUsernameError("Username 'alice' already exists")
        )

        with patch("routers.admin.users.UserService", return_value=svc):
            with pytest.raises(HTTPException) as exc_info:
                await create_user(
                    body=CreateUserRequest(username="alice", password="secret"),
                    user=User(username="admin", sub="admin", is_admin=True),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 409

    async def test_create_user_returns_400_for_weak_password(self):
        from routers.admin.common import CreateUserRequest
        from routers.admin.users import create_user

        svc = MagicMock()
        svc.create_local_user = AsyncMock(
            side_effect=PasswordPolicyError(
                "Password must be at least 12 characters long"
            )
        )

        with patch("routers.admin.users.UserService", return_value=svc):
            with pytest.raises(HTTPException) as exc_info:
                await create_user(
                    body=CreateUserRequest(username="alice", password="short"),
                    user=User(username="admin", sub="admin", is_admin=True),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 400

    async def test_set_user_password_returns_400_for_weak_password(self):
        from routers.admin.common import SetUserPasswordRequest
        from routers.admin.users import set_user_password

        svc = MagicMock()
        svc.get_user_by_sub = AsyncMock(return_value=SimpleNamespace(sub="app:alice"))
        svc.set_password = AsyncMock(
            side_effect=PasswordPolicyError("Password is too common")
        )

        with patch("routers.admin.users.UserService", return_value=svc):
            with pytest.raises(HTTPException) as exc_info:
                await set_user_password(
                    user_sub="app:alice",
                    body=SetUserPasswordRequest(password="password123"),
                    user=User(username="admin", sub="admin", is_admin=True),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Password is too common"

    async def test_update_user_returns_409_for_duplicate_username(self):
        from routers.admin.common import UpdateUserRequest
        from routers.admin.users import update_user

        svc = MagicMock()
        svc.update_user = AsyncMock(
            side_effect=DuplicateUsernameError("Username 'alice' already exists")
        )

        with patch("routers.admin.users.UserService", return_value=svc):
            with pytest.raises(HTTPException) as exc_info:
                await update_user(
                    user_sub="app:alice",
                    body=UpdateUserRequest(username="alice"),
                    user=User(username="admin", sub="admin", is_admin=True),
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 409


def test_yaml_settings_source_supports_auth_dev_groups_list(tmp_path, monkeypatch):
    from config import YamlSettingsSource

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "auth_dev_groups:\n  - admins\n  - developers\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_FILE", str(config_path))

    result = YamlSettingsSource(object)()

    assert result["AUTH_DEV_GROUPS_STR"] == "admins,developers"


def test_yaml_settings_source_derives_field_map_from_settings_fields():
    from config import Settings, YamlSettingsSource

    field_map = YamlSettingsSource(Settings).field_map

    for field_name in Settings.model_fields:
        assert field_map[field_name.lower()] == field_name

    assert field_map["public_base_url"] == "PUBLIC_BASE_URL"
    assert field_map["db_pool_size"] == "DB_POOL_SIZE"
    assert field_map["cors_allow_origins"] == "CORS_ALLOW_ORIGINS_STR"
    assert field_map["auth_dev_groups"] == "AUTH_DEV_GROUPS_STR"
    assert field_map["acl_admin_groups"] == "ACL_ADMIN_GROUPS_STR"


def test_yaml_settings_source_maps_password_policy_and_throttle_keys(
    tmp_path, monkeypatch
):
    from config import YamlSettingsSource

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "auth_password_min_length: 14\n"
        "auth_password_reject_common: true\n"
        "auth_login_throttle_enabled: true\n"
        "auth_login_max_attempts: 4\n"
        "auth_login_window_seconds: 60\n"
        "auth_login_lockout_seconds: 600\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_FILE", str(config_path))

    result = YamlSettingsSource(object)()

    assert result["AUTH_PASSWORD_MIN_LENGTH"] == 14
    assert result["AUTH_PASSWORD_REJECT_COMMON"] is True
    assert result["AUTH_LOGIN_THROTTLE_ENABLED"] is True
    assert result["AUTH_LOGIN_MAX_ATTEMPTS"] == 4
    assert result["AUTH_LOGIN_WINDOW_SECONDS"] == 60
    assert result["AUTH_LOGIN_LOCKOUT_SECONDS"] == 600


def test_yaml_settings_source_maps_extraction_chunk_strategy(tmp_path, monkeypatch):
    from config import YamlSettingsSource

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "document_extraction_chunk_strategy: selected\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_FILE", str(config_path))

    result = YamlSettingsSource(object)()

    assert result["DOCUMENT_EXTRACTION_CHUNK_STRATEGY"] == "selected"


def test_validate_local_password_rejects_short_password():
    settings = SimpleNamespace(
        AUTH_PASSWORD_MIN_LENGTH=12,
        AUTH_PASSWORD_REJECT_COMMON=True,
    )

    with pytest.raises(PasswordPolicyError) as exc_info:
        validate_local_password("short", settings)

    assert "at least 12 characters" in str(exc_info.value)


def test_validate_local_password_rejects_common_password():
    settings = SimpleNamespace(
        AUTH_PASSWORD_MIN_LENGTH=8,
        AUTH_PASSWORD_REJECT_COMMON=True,
    )

    with pytest.raises(PasswordPolicyError) as exc_info:
        validate_local_password("password123", settings)

    assert str(exc_info.value) == "Password is too common"


@pytest.mark.asyncio
async def test_set_password_validates_before_database_lookup():
    db = MagicMock()
    db.execute = AsyncMock()
    svc = UserService(db)

    with (
        patch(
            "config.get_settings",
            return_value=SimpleNamespace(
                AUTH_PASSWORD_MIN_LENGTH=12,
                AUTH_PASSWORD_REJECT_COMMON=True,
            ),
        ),
        pytest.raises(PasswordPolicyError),
    ):
        await svc.set_password("app:alice", "short")

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_local_user_delegates_local_identity_creation_to_set_password():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result
    svc = UserService(db)
    svc.set_password = AsyncMock()

    with patch(
        "config.get_settings",
        return_value=SimpleNamespace(
            AUTH_PASSWORD_MIN_LENGTH=12,
            AUTH_PASSWORD_REJECT_COMMON=True,
        ),
    ):
        created = await svc.create_local_user(
            username="admin",
            password="correct-horse-battery-staple",
        )

    assert isinstance(created, AppUser)
    svc.set_password.assert_awaited_once_with(
        created.sub,
        "correct-horse-battery-staple",
        must_change_password=False,
        commit=False,
    )
    added_objects = [call.args[0] for call in db.add.call_args_list]
    assert any(isinstance(item, AppUser) for item in added_objects)
    assert not any(isinstance(item, UserIdentity) for item in added_objects)
