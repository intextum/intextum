"""Service-level RLS coverage for admin, auth, and internal service contexts."""

from __future__ import annotations

import pytest

from models.user import User
from rls import internal_context, set_rls_context
from services.ai_settings import AiSettingsService
from services.connector import DataConnectorService, connector_registry
from services.event_outbox import EventOutboxService
from services.group import GroupService
from services.user import UserService
from services.worker import WorkerService
from tests.integration.rls_helpers import admin_context, session_factory


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_admin_services_manage_workers_groups_users_settings_and_connectors(
    rls_database,
):
    connector_registry.clear()
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())

            worker = await WorkerService(session).create_worker("Admin worker")
            token = await WorkerService(session).create_token(worker.id)
            assert worker.id
            assert token

            group = await GroupService(session).create_group(
                slug="Reviewers",
                display_name="Reviewers",
                proxy_aliases=["External Reviewers"],
            )
            assert group.slug == "reviewers"

            user = await UserService(session).create_local_user(
                username="reviewer",
                password="correct-horse-battery-staple",
                group_slugs=["reviewers"],
            )
            assert user.username == "reviewer"

            settings = await AiSettingsService(session).update_settings(
                {"chat_model": "integration-chat-model"},
                updated_by="sub-admin",
            )
            chat_model = next(
                item for item in settings.items if item.key == "chat_model"
            )
            assert chat_model.value == "integration-chat-model"

            connector = await DataConnectorService(session).create_connector(
                uuid="docs-source",
                name="Docs Source",
                connector_type="local_fs",
                path="/tmp/rls-docs-source",
                watch=False,
                initial_scan=False,
            )
            assert connector.uuid == "docs-source"
            assert await DataConnectorService(session).delete_connector(
                "docs-source",
                force=True,
            )
    finally:
        connector_registry.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_context_syncs_proxy_user_memberships(rls_database):
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await GroupService(session).create_group(
                slug="reviewers",
                display_name="Reviewers",
                proxy_aliases=["External Reviewers"],
            )

            await set_rls_context(session, internal_context("auth"))
            user = await UserService(session).ensure_proxy_user(
                provider_subject="proxy-user-1",
                username="proxy-reviewer",
                email="proxy@example.test",
                display_name="Proxy Reviewer",
                external_groups=["external reviewers"],
            )

            assert user.username == "proxy-reviewer"
            assert user.groups == ["reviewers"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_event_outbox_context_dispatches_user_event(rls_database):
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(
                session,
                admin_context(),
            )
            await UserService(session).ensure_user(
                User(username="alice", sub="sub-alice", groups=[], is_admin=False)
            )

            EventOutboxService(session).enqueue_user_event(
                user_sub="sub-alice",
                kind="integration.event",
                resource_type="integration",
                resource_id="resource-1",
                status="ok",
                metadata={"source": "rls"},
            )
            await session.commit()

            await set_rls_context(session, internal_context("event_outbox"))
            processed = await EventOutboxService(session).dispatch_pending(limit=10)

            assert processed == 1
    finally:
        await engine.dispose()
