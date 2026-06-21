"""Fixtures for integration tests against real dependencies."""

import importlib
import os
import socket
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


def _owner_conninfo(*, database: str = "postgres") -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return f"host={host} port={port} dbname={database} user={user} password={password}"


def _app_conninfo(*, database: str) -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_APP_USER", "dms_app")
    password = os.environ.get("POSTGRES_APP_PASSWORD", "dms_app")
    return f"host={host} port={port} dbname={database} user={user} password={password}"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


@contextmanager
def _temporary_env(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _upgrade_database(database: str) -> None:
    with _temporary_env(
        {
            "POSTGRES_DB": database,
            "POSTGRES_APP_USER": os.environ.get("POSTGRES_APP_USER", "dms_app"),
            "POSTGRES_APP_PASSWORD": os.environ.get("POSTGRES_APP_PASSWORD", "dms_app"),
        }
    ):
        cfg = Config(str(_backend_root() / "alembic.ini"))
        cfg.set_main_option("script_location", str(_backend_root() / "alembic"))
        cfg.set_main_option("prepend_sys_path", str(_backend_root()))
        command.upgrade(cfg, "head")


def _wait_for_postgres(host: str, port: int, timeout_s: float = 20.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _drop_database_bound_app_modules() -> None:
    """Force app modules with database globals to bind to the test database."""
    reload_prefixes = (
        "auth.worker_auth",
        "chat.checkpointer",
        "database",
        "main",
        "routers",
        "services.watcher",
        "services.watcher_runtime",
    )
    for module_name in list(sys.modules):
        if module_name in reload_prefixes or module_name.startswith(
            tuple(f"{prefix}." for prefix in reload_prefixes)
        ):
            sys.modules.pop(module_name, None)


@pytest.fixture(scope="session")
def docker_compose_file():
    return str(Path(__file__).with_name("docker-compose.yml"))


@pytest.fixture(scope="session")
def integration_environment(request, tmp_path_factory):
    """Configure runtime env for integration tests and verify dependencies are up."""
    if os.environ.get("INTEXTUM_RUN_INTEGRATION") != "1":
        pytest.skip(
            "Set INTEXTUM_RUN_INTEGRATION=1 to run integration tests.",
            allow_module_level=True,
        )

    use_external_postgres = any(
        key in os.environ for key in ("POSTGRES_HOST", "POSTGRES_PORT")
    )
    data_root = tmp_path_factory.mktemp("integration-data")
    os.environ["CONFIG_FILE"] = ""
    os.environ["OPENAI_API_KEY"] = "test"
    os.environ.setdefault("POSTGRES_USER", "postgres")
    os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
    os.environ.setdefault("POSTGRES_DB", "intextum_db")
    os.environ.setdefault("POSTGRES_APP_USER", "dms_app")
    os.environ.setdefault("POSTGRES_APP_PASSWORD", "dms_app")
    os.environ["DATA_VOLUME"] = str(data_root)

    if not use_external_postgres:
        docker_ip = request.getfixturevalue("docker_ip")
        docker_services = request.getfixturevalue("docker_services")
        os.environ["POSTGRES_HOST"] = docker_ip
        os.environ["POSTGRES_PORT"] = str(docker_services.port_for("postgres", 5432))
    else:
        os.environ.setdefault("POSTGRES_HOST", "localhost")
        os.environ.setdefault("POSTGRES_PORT", "5432")

    postgres_host = os.environ["POSTGRES_HOST"]
    postgres_port = int(os.environ["POSTGRES_PORT"])

    if not _wait_for_postgres(postgres_host, postgres_port):
        pytest.skip(
            f"Postgres not reachable at {postgres_host}:{postgres_port}",
            allow_module_level=True,
        )

    return {
        "postgres_host": postgres_host,
        "postgres_port": postgres_port,
    }


@pytest.fixture
def rls_database(integration_environment):
    """Create a fresh database and apply the Alembic baseline."""
    database = f"intextum_rls_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(_owner_conninfo(), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{database}"')

    env = {
        "POSTGRES_DB": database,
        "POSTGRES_APP_USER": os.environ.get("POSTGRES_APP_USER", "dms_app"),
        "POSTGRES_APP_PASSWORD": os.environ.get("POSTGRES_APP_PASSWORD", "dms_app"),
    }
    try:
        with _temporary_env(env):
            _upgrade_database(database)
        yield database
    finally:
        with psycopg.connect(_owner_conninfo(), autocommit=True) as conn:
            conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (database,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{database}"')


@pytest.fixture
def app_conn(rls_database):
    """Open a psycopg connection as the non-owner app role."""
    with psycopg.connect(_app_conninfo(database=rls_database)) as conn:
        yield conn


@pytest.fixture
def integration_client(integration_environment):
    """Build an app client wired to real external services."""
    _upgrade_database(os.environ["POSTGRES_DB"])

    import config
    import clients

    config.get_settings.cache_clear()
    for attr in (
        "get_embedding_client",
        "get_async_embedding_client",
        "get_chat_model",
    ):
        client_factory = getattr(clients, attr, None)
        if client_factory is not None and hasattr(client_factory, "cache_clear"):
            client_factory.cache_clear()

    _drop_database_bound_app_modules()
    main = importlib.import_module("main")

    with TestClient(main.app, raise_server_exceptions=False) as client:
        yield client
