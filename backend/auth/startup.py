"""Auth startup helpers."""

from __future__ import annotations

from rls import internal_context, rls_session
from services.user import UserService
from services.valkey import is_valkey_configured, probe_valkey


async def bootstrap_local_auth(settings, *, session_factory) -> None:
    """Validate local-auth dependencies and bootstrap the local admin user."""
    if not settings.AUTH_LOCAL_ENABLED:
        return

    if not is_valkey_configured():
        raise RuntimeError("AUTH_LOCAL_ENABLED requires VALKEY_URL to be configured")
    if not await probe_valkey():
        raise RuntimeError("AUTH_LOCAL_ENABLED requires a reachable Valkey instance")

    async with rls_session(session_factory, internal_context("auth")) as db:
        await UserService(db).bootstrap_local_admin(settings)
