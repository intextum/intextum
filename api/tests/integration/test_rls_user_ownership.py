"""Service-level RLS coverage for user-owned rows and user management."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm.exc import StaleDataError

from models.notification_preferences import NotificationPreferences
from rls import set_rls_context
from services.group import GroupService
from services.notification_preferences import NotificationPreferencesService
from services.user import UserService
from tests.integration.rls_helpers import admin_context, session_factory, user_context


pytestmark = pytest.mark.integration


def _group_slugs(user) -> list[str]:
    return sorted(membership.group_slug for membership in user.group_memberships)


async def _create_users(database: str):
    engine, factory = session_factory(database=database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await GroupService(session).create_group(
                slug="reviewers",
                display_name="Reviewers",
            )
            alice = await UserService(session).create_local_user(
                username="alice",
                password="correct-horse-battery-staple",
                email="alice@example.test",
                display_name="Alice",
                group_slugs=["reviewers"],
            )
            bob = await UserService(session).create_local_user(
                username="bob",
                password="correct-horse-battery-staple",
                email="bob@example.test",
                display_name="Bob",
            )
            admin = await UserService(session).create_local_user(
                username="second-admin",
                password="correct-horse-battery-staple",
                is_admin=True,
            )
            disabled = await UserService(session).create_local_user(
                username="disabled-user",
                password="correct-horse-battery-staple",
                is_disabled=True,
            )
            return alice, bob, admin, disabled
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_owned_notification_preferences_are_isolated(rls_database):
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, user_context(user_sub="sub-alice"))
            prefs = NotificationPreferences()
            prefs.chat.completed = False
            updated = await NotificationPreferencesService(session).update_preferences(
                "sub-alice",
                prefs,
            )
            assert updated.chat.completed is False

            with pytest.raises(ProgrammingError):
                await NotificationPreferencesService(session).update_preferences(
                    "sub-bob",
                    prefs,
                )

        async with factory() as session:
            await set_rls_context(session, user_context(user_sub="sub-bob"))
            bob_prefs = await NotificationPreferencesService(session).get_preferences(
                "sub-bob"
            )
            assert bob_prefs == NotificationPreferences()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_normal_user_reads_self_but_cannot_manage_users(rls_database):
    alice, bob, admin, disabled = await _create_users(rls_database)

    assert admin.is_admin is True
    assert disabled.is_disabled is True

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, user_context(user_sub=alice.sub))
            own_user = await UserService(session).get_user_by_sub(alice.sub)
            other_user = await UserService(session).get_user_by_sub(bob.sub)

            assert own_user is not None
            assert own_user.username == "alice"
            assert other_user is None

        with pytest.raises((ProgrammingError, StaleDataError)):
            async with factory() as session:
                await set_rls_context(session, user_context(user_sub=alice.sub))
                await UserService(session).update_user(
                    user_sub=alice.sub,
                    is_admin=True,
                    group_slugs=[],
                )

        async with factory() as session:
            await set_rls_context(session, user_context(user_sub=alice.sub))
            updated = await UserService(session).update_user(
                user_sub=bob.sub,
                display_name="Mallory",
            )
            assert updated is None

        with pytest.raises(ProgrammingError):
            async with factory() as session:
                await set_rls_context(session, user_context(user_sub=alice.sub))
                await UserService(session).create_local_user(
                    username="mallory",
                    password="correct-horse-battery-staple",
                )
    finally:
        await engine.dispose()

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            alice_after = await UserService(session).get_user_by_sub(alice.sub)
            bob_after = await UserService(session).get_user_by_sub(bob.sub)

            assert alice_after is not None
            assert alice_after.is_admin is False
            assert _group_slugs(alice_after) == ["reviewers"]
            assert bob_after is not None
            assert bob_after.display_name == "Bob"
    finally:
        await engine.dispose()
