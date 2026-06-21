"""Provider-based request authentication resolution."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from auth.helpers import parse_groups_header, parse_int_list_header, parse_optional_int
from config import get_settings
from models.user import User
from rls import internal_context, rls_session
from services.auth import LocalSessionService
from services.user import UserService


@dataclass
class ProxyClaims:
    sub: str
    username: str
    email: str | None
    preferred_username: str | None
    uid: int | None
    gids: list[int]
    groups: list[str]


def build_auth_provider_status() -> dict[str, Any]:
    """Return public provider capability flags for the frontend."""
    settings = get_settings()
    return {
        "local_enabled": bool(settings.AUTH_LOCAL_ENABLED),
        "proxy_enabled": bool(
            settings.AUTH_PROXY_ENABLED and settings.AUTH_PROXY_SECRET
        ),
        "dev_enabled": bool(settings.AUTH_DEV_ENABLED),
        "session_cookie_name": settings.AUTH_SESSION_COOKIE_NAME,
        "csrf_cookie_name": settings.AUTH_CSRF_COOKIE_NAME,
        "csrf_header_name": settings.AUTH_CSRF_HEADER_NAME,
    }


def _extract_proxy_claims(request: Request) -> ProxyClaims | None:
    settings = get_settings()
    if not settings.AUTH_PROXY_ENABLED or not settings.AUTH_PROXY_SECRET:
        return None

    proxy_secret = request.headers.get("X-Proxy-Secret", "")
    if not proxy_secret or not secrets.compare_digest(
        proxy_secret, settings.AUTH_PROXY_SECRET
    ):
        return None

    sub = (request.headers.get(settings.AUTH_HEADER_SUB) or "").strip()
    if not sub:
        return None

    login_name = (request.headers.get(settings.AUTH_HEADER_USER) or "").strip()
    email = request.headers.get(settings.AUTH_HEADER_EMAIL)
    preferred_username = request.headers.get(settings.AUTH_HEADER_PREFERRED_USERNAME)
    username = login_name or (preferred_username or "").strip() or sub
    uid = parse_optional_int(request.headers.get(settings.AUTH_HEADER_UID))
    gids = parse_int_list_header(request.headers.get(settings.AUTH_HEADER_GIDS, ""))
    groups = parse_groups_header(request.headers.get(settings.AUTH_HEADER_GROUPS, ""))
    for group in groups:
        gid = parse_optional_int(group)
        if gid is not None and gid not in gids:
            gids.append(gid)

    return ProxyClaims(
        sub=sub,
        username=username,
        email=email,
        preferred_username=preferred_username,
        uid=uid,
        gids=gids,
        groups=groups,
    )


async def resolve_request_user(
    request: Request,
    *,
    session_factory,
) -> User | None:
    """Resolve the current request user by provider precedence."""
    settings = get_settings()
    session_id = ""
    if settings.AUTH_LOCAL_ENABLED:
        session_id = request.cookies.get(settings.AUTH_SESSION_COOKIE_NAME, "")
    claims = _extract_proxy_claims(request)

    if not session_id and claims is None and not settings.AUTH_DEV_ENABLED:
        return None

    async with rls_session(session_factory, internal_context("auth")) as db:
        user_service = UserService(db)

        if session_id:
            session_service = LocalSessionService()
            session = await session_service.get_session(session_id)
            if session is not None:
                app_user = await user_service.get_user_by_sub(session.user_sub)
                if (
                    app_user is not None
                    and not app_user.is_disabled
                    and int(app_user.session_version or 1)
                    == int(session.session_version)
                ):
                    user = await user_service.build_user_context(
                        user_sub=app_user.sub,
                        auth_provider=session.auth_provider,
                    )
                    if user is not None:
                        user.csrf_token = session.csrf_token
                        request.state.auth_session_id = session.session_id
                        request.state.auth_csrf_token = session.csrf_token
                        request.state.auth_provider = session.auth_provider
                        return user
                await session_service.revoke_session(session_id)

        if claims is not None:
            proxy_admin = any(
                group.lower() in {item.lower() for item in settings.ACL_ADMIN_GROUPS}
                for group in claims.groups
            )
            user = await user_service.ensure_proxy_user(
                provider_subject=claims.sub,
                username=claims.username,
                email=claims.email,
                display_name=claims.preferred_username or claims.username,
                external_groups=claims.groups,
                preferred_username=claims.preferred_username,
                uid=claims.uid,
                gids=claims.gids,
                is_admin=proxy_admin,
            )
            request.state.auth_provider = "proxy"
            return user

        if settings.AUTH_DEV_ENABLED:
            user = await user_service.ensure_dev_user(
                provider_subject=settings.AUTH_DEV_SUB,
                username=settings.AUTH_DEV_USERNAME,
                email=settings.AUTH_DEV_EMAIL or None,
                groups=settings.AUTH_DEV_GROUPS,
            )
            request.state.auth_provider = "dev"
            return user

    return None
