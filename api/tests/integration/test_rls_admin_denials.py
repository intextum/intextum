"""Service-level RLS coverage for admin-only service denials."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from models.content.enrichment_catalog import ContentEnrichmentDocumentClassInput
from rls import set_rls_context
from services.ai_settings import AiSettingsService
from services.connector import DataConnectorService, connector_registry
from services.content.enrichment.catalog import ContentEnrichmentCatalogService
from services.group import GroupService
from services.permission import PermissionService
from services.worker import WorkerService
from tests.integration.rls_helpers import admin_context, session_factory, user_context


pytestmark = pytest.mark.integration


DeniedOperation = Callable[[AsyncSession], Awaitable[object]]


async def _assert_user_operation_denied(
    database: str,
    operation: DeniedOperation,
) -> None:
    engine, factory = session_factory(database=database)
    try:
        with pytest.raises(ProgrammingError):
            async with factory() as session:
                await set_rls_context(session, user_context(user_sub="sub-alice"))
                await operation(session)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_non_admin_cannot_change_admin_settings_or_catalog(rls_database):
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await AiSettingsService(session).update_settings(
                {"chat_model": "protected-model"},
                updated_by="sub-admin",
            )
    finally:
        await engine.dispose()

    await _assert_user_operation_denied(
        rls_database,
        lambda session: AiSettingsService(session).update_settings(
            {"chat_model": "forbidden-model"},
            updated_by="sub-alice",
        ),
    )

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, user_context(user_sub="sub-alice"))
            await AiSettingsService(session).reset_settings(keys=["chat_model"])

        async with factory() as session:
            await set_rls_context(session, admin_context())
            settings = await AiSettingsService(session).get_admin_response()
            chat_model = next(
                item for item in settings.items if item.key == "chat_model"
            )
            assert chat_model.value == "protected-model"
    finally:
        await engine.dispose()

    await _assert_user_operation_denied(
        rls_database,
        lambda session: ContentEnrichmentCatalogService(session).replace_catalog(
            document_classes=[
                ContentEnrichmentDocumentClassInput(
                    id="invoice",
                    name="Invoice",
                    description="Invoices",
                )
            ],
        ),
    )


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_admin_resources(rls_database):
    connector_registry.clear()
    try:
        await _assert_user_operation_denied(
            rls_database,
            lambda session: GroupService(session).create_group(
                slug="blocked",
                display_name="Blocked",
            ),
        )
        await _assert_user_operation_denied(
            rls_database,
            lambda session: WorkerService(session).create_worker("Blocked worker"),
        )
        await _assert_user_operation_denied(
            rls_database,
            lambda session: DataConnectorService(session).create_connector(
                uuid="blocked-source",
                name="Blocked Source",
                connector_type="local_fs",
                path="/tmp/blocked-source",
                watch=False,
                initial_scan=False,
            ),
        )
        await _assert_user_operation_denied(
            rls_database,
            lambda session: PermissionService(session).set_permission(
                "folder-1",
                "sub:sub-alice",
                access="allow",
                granted_by="alice",
            ),
        )
    finally:
        connector_registry.clear()


@pytest.mark.asyncio
async def test_admin_can_change_representative_admin_resources(rls_database):
    connector_registry.clear()
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            settings = await AiSettingsService(session).update_settings(
                {"chat_model": "allowed-model"},
                updated_by="sub-admin",
            )
            assert (
                next(item for item in settings.items if item.key == "chat_model").value
                == "allowed-model"
            )

            group = await GroupService(session).create_group(
                slug="allowed",
                display_name="Allowed",
            )
            assert group.slug == "allowed"

            worker = await WorkerService(session).create_worker("Allowed worker")
            assert worker.id

            connector = await DataConnectorService(session).create_connector(
                uuid="allowed-source",
                name="Allowed Source",
                connector_type="local_fs",
                path="/tmp/allowed-source",
                watch=False,
                initial_scan=False,
            )
            assert connector.uuid == "allowed-source"

            permission = await PermissionService(session).set_permission(
                "folder-1",
                "group:allowed",
                access="allow",
                granted_by="admin",
            )
            assert permission.trustee == "group:allowed"
    finally:
        connector_registry.clear()
        await engine.dispose()
