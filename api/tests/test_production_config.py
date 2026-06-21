"""Tests for production-mode configuration validation."""

from types import SimpleNamespace

import pytest

from config import collect_production_config_errors, is_production_env
from config import validate_production_settings


def _settings(**overrides):
    values = {
        "APP_ENV": "production",
        "AUTH_DEV_ENABLED": False,
        "AUTH_LOCAL_ENABLED": True,
        "AUTH_PROXY_ENABLED": False,
        "AUTH_PROXY_SECRET": "",
        "AUTH_SESSION_SECURE_COOKIE": True,
        "CORS_ALLOW_ORIGINS": ["https://app.example.org"],
        "ENCRYPTION_KEY": "test-fernet-key",
        "POSTGRES_APP_PASSWORD": "not-the-app-default",
        "POSTGRES_PASSWORD": "not-the-default",
        "VALKEY_URL": "redis://valkey:6379/0",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_is_production_env_accepts_prod_aliases():
    assert is_production_env(_settings(APP_ENV="production")) is True
    assert is_production_env(_settings(APP_ENV="prod")) is True
    assert is_production_env(_settings(APP_ENV="development")) is False


def test_development_mode_does_not_report_production_errors():
    settings = _settings(
        APP_ENV="development",
        AUTH_DEV_ENABLED=True,
        CORS_ALLOW_ORIGINS=[],
        ENCRYPTION_KEY="",
        POSTGRES_APP_PASSWORD="dms_app",
        POSTGRES_PASSWORD="postgres",
        VALKEY_URL="",
    )

    assert collect_production_config_errors(settings) == []
    validate_production_settings(settings)


def test_valid_local_auth_production_config_passes():
    validate_production_settings(_settings())


def test_valid_proxy_auth_production_config_passes():
    validate_production_settings(
        _settings(
            AUTH_LOCAL_ENABLED=False,
            AUTH_PROXY_ENABLED=True,
            AUTH_PROXY_SECRET="shared-secret",
            AUTH_SESSION_SECURE_COOKIE=False,
            VALKEY_URL="",
        )
    )


def test_production_validation_collects_unsafe_defaults():
    settings = _settings(
        AUTH_DEV_ENABLED=True,
        AUTH_LOCAL_ENABLED=True,
        AUTH_PROXY_ENABLED=True,
        AUTH_PROXY_SECRET="",
        AUTH_SESSION_SECURE_COOKIE=False,
        CORS_ALLOW_ORIGINS=["*"],
        ENCRYPTION_KEY="",
        POSTGRES_APP_PASSWORD="dms_app",
        POSTGRES_PASSWORD="postgres",
        VALKEY_URL="",
    )

    errors = collect_production_config_errors(settings)

    assert "AUTH_DEV_ENABLED must be false in production" in errors
    assert "AUTH_LOCAL_ENABLED requires VALKEY_URL in production" in errors
    assert (
        "AUTH_SESSION_SECURE_COOKIE must be true for local auth in production" in errors
    )
    assert "AUTH_PROXY_ENABLED requires AUTH_PROXY_SECRET in production" in errors
    assert "CORS_ALLOW_ORIGINS must not contain '*' in production" in errors
    assert "ENCRYPTION_KEY must be set in production" in errors
    assert "POSTGRES_PASSWORD must be set to a non-default value" in errors
    assert "POSTGRES_APP_PASSWORD must be set to a non-default value" in errors


def test_production_validation_raises_with_actionable_message():
    settings = _settings(CORS_ALLOW_ORIGINS=[])

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_settings(settings)

    assert "Unsafe production configuration" in str(exc_info.value)
    assert "CORS_ALLOW_ORIGINS must be set in production" in str(exc_info.value)
