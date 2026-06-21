"""Authentication and local session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user, require_user
from auth.payloads import user_payload
from auth.providers import build_auth_provider_status
from database import get_db
from models.user import User
from services.auth import LocalLoginThrottle, LocalSessionService
from services.password_policy import PasswordPolicyError
from services.user import UserService

router = APIRouter(prefix="/auth")


class LocalLoginRequest(BaseModel):
    username_or_email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


def _set_auth_cookies(response: Response, *, session, settings) -> None:
    response.set_cookie(
        settings.AUTH_SESSION_COOKIE_NAME,
        session.session_id,
        httponly=True,
        secure=settings.AUTH_SESSION_SECURE_COOKIE,
        samesite="lax",
        path="/",
        max_age=settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    response.set_cookie(
        settings.AUTH_CSRF_COOKIE_NAME,
        session.csrf_token,
        httponly=False,
        secure=settings.AUTH_SESSION_SECURE_COOKIE,
        samesite="lax",
        path="/",
        max_age=settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )


def _clear_auth_cookies(response: Response, *, settings) -> None:
    response.delete_cookie(settings.AUTH_SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(settings.AUTH_CSRF_COOKIE_NAME, path="/")


@router.get("/providers")
async def get_auth_providers() -> dict:
    """Return public auth capability flags for the frontend."""
    payload = build_auth_provider_status()
    payload["proxy_login_url"] = "/oauth2/start"
    payload["proxy_logout_url"] = "/oauth2/sign_out"
    return payload


@router.post("/login")
async def login_local(
    body: LocalLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Authenticate using local credentials and create a Valkey-backed session."""
    from config import get_settings

    settings = get_settings()
    if not settings.AUTH_LOCAL_ENABLED:
        raise HTTPException(status_code=404, detail="Local auth is disabled")

    identifier = body.username_or_email.strip()
    client_ip = request.client.host if request.client is not None else ""
    throttle = LocalLoginThrottle()
    throttle_state = await throttle.check_allowed(
        identifier=identifier,
        client_ip=client_ip,
    )
    if not throttle_state.allowed:
        retry_after = throttle_state.retry_after_seconds or 1
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = await UserService(db).authenticate_local(
        identifier=identifier,
        password=body.password,
    )
    if user is None:
        throttle_state = await throttle.record_failure(
            identifier=identifier,
            client_ip=client_ip,
        )
        if not throttle_state.allowed:
            retry_after = throttle_state.retry_after_seconds or 1
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    app_user = await UserService(db).get_user_by_sub(user.require_stable_sub())
    if app_user is None:
        await throttle.record_failure(identifier=identifier, client_ip=client_ip)
        raise HTTPException(status_code=401, detail="Local user missing")
    await throttle.clear(identifier=identifier, client_ip=client_ip)
    session = await LocalSessionService().create_session(
        user_sub=app_user.sub,
        session_version=int(app_user.session_version or 1),
        auth_provider="local",
    )
    user.csrf_token = session.csrf_token
    _set_auth_cookies(response, session=session, settings=settings)
    return user_payload(user)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: User | None = Depends(get_current_user),
) -> dict:
    """Revoke the local session if present and clear auth cookies."""
    from config import get_settings

    settings = get_settings()
    session_id = request.cookies.get(settings.AUTH_SESSION_COOKIE_NAME, "")
    if session_id:
        await LocalSessionService().revoke_session(session_id)
    _clear_auth_cookies(response, settings=settings)
    return {
        "logged_out": True,
        "auth_provider": user.auth_provider if user is not None else "anonymous",
        "proxy_logout_url": "/oauth2/sign_out",
    }


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change the current user's local password."""
    from config import get_settings

    settings = get_settings()
    svc = UserService(db)
    try:
        changed = await svc.change_password(
            user_sub=user.require_stable_sub(),
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=400, detail="Current password is invalid")
    if settings.AUTH_LOCAL_ENABLED:
        app_user = await svc.get_user_by_sub(user.require_stable_sub())
        if app_user is None:
            raise HTTPException(status_code=401, detail="Local user missing")
        session = await LocalSessionService().create_session(
            user_sub=app_user.sub,
            session_version=int(app_user.session_version or 1),
            auth_provider="local",
        )
        _set_auth_cookies(response, session=session, settings=settings)
    return {"updated": True}
