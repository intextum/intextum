"""Tests for Postgres row-level-security context helpers.

The policy DDL itself lives in ``backend/sql/rls/*.sql`` and is exercised by
the integration tests under ``backend/tests/integration``. This module only
covers the Python-side context machinery.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models.user import User
from rls import (
    RlsContext,
    chat_runner_context,
    set_rls_context,
    user_context,
    worker_task_context,
)


def test_user_context_serializes_current_trustees_and_admin_marker():
    context = user_context(
        User(
            username="alice",
            sub=" app:alice ",
            groups=["Users", "admins"],
            is_admin=True,
        )
    )

    assert context.actor == "user"
    assert context.user_sub == "app:alice"
    assert context.is_admin is True
    assert context.trustees == [
        "everyone",
        "sub:app:alice",
        "group:users",
        "group:admins",
        "__acl_admin__",
    ]


def test_chat_runner_context_inherits_run_owner_identity():
    context = chat_runner_context(
        User(username="bob", sub="app:bob", groups=["editors"])
    )

    assert context.actor == "chat_runner"
    assert context.user_sub == "app:bob"
    assert context.is_admin is False
    assert context.trustees == [
        "everyone",
        "sub:app:bob",
        "group:editors",
    ]


@pytest.mark.asyncio
async def test_set_rls_context_uses_transaction_local_settings():
    db = SimpleNamespace(
        sync_session=SimpleNamespace(info={}),
        execute=AsyncMock(),
    )
    context = worker_task_context(
        worker_id="worker-1",
        task_id="task-1",
        content_item_id="content-1",
    )

    await set_rls_context(db, context)  # type: ignore[arg-type]

    assert db.sync_session.info["rls_context"] == context
    sql, params = db.execute.await_args.args
    assert "set_config('app.actor'" in str(sql)
    assert params["actor"] == "worker_task"
    assert params["worker_id"] == "worker-1"
    assert params["task_id"] == "task-1"
    assert params["content_item_id"] == "content-1"
    assert params["trustees"] == "[]"


def test_context_params_serializes_trustees_as_json():
    params = RlsContext(actor="user", trustees=["everyone", "group:users"]).params()

    assert params["trustees"] == '["everyone", "group:users"]'
    assert params["is_admin"] == "false"
