"""Tests for worker management router dependencies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models.user import User
from routers.workers import get_worker_service


@pytest.mark.asyncio
async def test_worker_service_dependency_applies_admin_rls_context():
    db = SimpleNamespace(
        sync_session=SimpleNamespace(info={}),
        execute=AsyncMock(),
    )
    admin = User(
        username="admin",
        sub="sub-admin",
        groups=["admins"],
        is_admin=True,
    )

    service = await get_worker_service(user=admin, db=db)  # type: ignore[arg-type]

    assert service.db is db
    sql, params = db.execute.await_args.args
    assert "set_config('app.actor'" in str(sql)
    assert params["actor"] == "user"
    assert params["is_admin"] == "true"
