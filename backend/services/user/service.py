"""User and identity management services."""

from __future__ import annotations

import time
from collections.abc import Iterable
from uuid import uuid4

from pwdlib import PasswordHash
from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.sqlalchemy_models import (
    AppUser,
    GroupExternalAlias,
    GroupMembership,
    LocalCredential,
    UserIdentity,
    utc_now,
)
from models.user import User
from services.password_policy import PasswordPolicyError, validate_local_password

LOCAL_PROVIDER = "local"
PROXY_PROVIDER = "proxy"
DEV_PROVIDER = "dev"
MANUAL_GROUP_SOURCE = "manual"
PROXY_GROUP_SOURCE = "proxy"
DEFAULT_AUTH_DISPLAY_SOURCE = PROXY_PROVIDER

_recently_seen: dict[str, float] = {}
_CACHE_TTL_SECONDS = 300
_password_hasher = PasswordHash.recommended()


class DuplicateUsernameError(ValueError):
    """Raised when a user-managed username is already taken."""


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    normalized = email.strip()
    return normalized if "@" in normalized else None


def _normalize_group_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        token = value.strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


class UserService:
    """Manages canonical users, linked identities, credentials, and memberships."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _username_exists(
        self, username: str, *, exclude_sub: str | None = None
    ) -> bool:
        stmt = select(AppUser.sub).where(AppUser.username == username)
        if exclude_sub is not None:
            stmt = stmt.where(AppUser.sub != exclude_sub)
        result = await self.db.execute(stmt.limit(1))
        return result.scalar_one_or_none() is not None

    async def _dedupe_username(
        self, preferred_username: str, *, exclude_sub: str | None = None
    ) -> str:
        base = preferred_username.strip() or f"user-{uuid4().hex[:8]}"
        candidate = base
        suffix = 2
        while await self._username_exists(candidate, exclude_sub=exclude_sub):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    async def _require_available_username(
        self, preferred_username: str, *, exclude_sub: str | None = None
    ) -> str:
        username = preferred_username.strip() or f"user-{uuid4().hex[:8]}"
        if await self._username_exists(username, exclude_sub=exclude_sub):
            raise DuplicateUsernameError(f"Username '{username}' already exists")
        return username

    @staticmethod
    def _new_app_sub() -> str:
        return f"app:{uuid4().hex}"

    @staticmethod
    def _with_user_relationships(stmt):
        return stmt.options(
            selectinload(AppUser.identities),
            selectinload(AppUser.group_memberships),
            selectinload(AppUser.local_credentials),
        )

    async def _load_user_with_relationships(self, sub: str) -> AppUser | None:
        stmt = self._with_user_relationships(select(AppUser).where(AppUser.sub == sub))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _replace_group_memberships(
        self,
        *,
        user_sub: str,
        group_slugs: Iterable[str],
        source: str,
    ) -> None:
        await self.db.execute(
            delete(GroupMembership).where(
                GroupMembership.user_sub == user_sub,
                GroupMembership.source == source,
            )
        )
        for slug in _normalize_group_values(group_slugs):
            self.db.add(
                GroupMembership(
                    user_sub=user_sub,
                    group_slug=slug,
                    source=source,
                )
            )

    async def list_effective_group_slugs(self, user_sub: str) -> list[str]:
        result = await self.db.execute(
            select(GroupMembership.group_slug)
            .where(GroupMembership.user_sub == user_sub)
            .order_by(GroupMembership.group_slug)
        )
        return _normalize_group_values(result.scalars().all())

    async def sync_proxy_memberships(
        self, *, user_sub: str, external_groups: Iterable[str]
    ) -> list[str]:
        normalized_external = _normalize_group_values(external_groups)
        if normalized_external:
            alias_result = await self.db.execute(
                select(
                    GroupExternalAlias.group_slug, GroupExternalAlias.external_value
                ).where(
                    GroupExternalAlias.provider == PROXY_PROVIDER,
                    GroupExternalAlias.external_value.in_(normalized_external),
                )
            )
            mapped_group_slugs = _normalize_group_values(
                row.group_slug for row in alias_result.all()
            )
        else:
            mapped_group_slugs = []

        await self._replace_group_memberships(
            user_sub=user_sub,
            group_slugs=mapped_group_slugs,
            source=PROXY_GROUP_SOURCE,
        )
        return mapped_group_slugs

    async def _to_user_context(
        self,
        app_user: AppUser,
        *,
        auth_provider: str,
        preferred_username: str | None = None,
        uid: int | None = None,
        gids: list[int] | None = None,
    ) -> User:
        groups = await self.list_effective_group_slugs(app_user.sub)
        return User(
            username=app_user.username,
            sub=app_user.sub,
            email=app_user.email,
            groups=groups,
            auth_provider=auth_provider,
            is_admin=bool(app_user.is_admin),
            is_disabled=bool(app_user.is_disabled),
            must_change_password=bool(
                app_user.local_credentials.must_change_password
                if app_user.local_credentials is not None
                else False
            ),
            preferred_username=(
                preferred_username or app_user.display_name or app_user.username
            ),
            uid=uid,
            gids=list(gids or []),
        )

    async def build_user_context(
        self,
        *,
        user_sub: str,
        auth_provider: str,
        preferred_username: str | None = None,
        uid: int | None = None,
        gids: list[int] | None = None,
    ) -> User | None:
        app_user = await self._load_user_with_relationships(user_sub)
        if app_user is None:
            return None
        return await self._to_user_context(
            app_user,
            auth_provider=auth_provider,
            preferred_username=preferred_username,
            uid=uid,
            gids=gids,
        )

    async def ensure_user(self, user: User) -> None:
        """Compatibility upsert for tests and non-provider-managed callers."""
        sub = user.require_stable_sub()
        username = await self._dedupe_username(
            user.username.strip() or sub, exclude_sub=sub
        )
        display_name = user.display_name.strip() or username
        email = _normalize_email(user.email)

        now = time.monotonic()
        last = _recently_seen.get(sub, 0.0)
        if now - last < _CACHE_TTL_SECONDS:
            return

        now_ts = utc_now()
        stmt = (
            pg_insert(AppUser)
            .values(
                sub=sub,
                username=username,
                email=email,
                display_name=display_name,
                auth_display_source=DEFAULT_AUTH_DISPLAY_SOURCE,
                is_admin=user.is_admin,
                is_disabled=False,
                session_version=1,
                first_seen_at=now_ts,
                last_seen_at=now_ts,
            )
            .on_conflict_do_update(
                index_elements=["sub"],
                set_={
                    "username": username,
                    "email": email,
                    "display_name": display_name,
                    "last_seen_at": now_ts,
                    "is_admin": user.is_admin,
                },
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
        _recently_seen[sub] = now

    async def list_users(self) -> list[AppUser]:
        """List all known users with auth/group relationships eagerly loaded."""
        result = await self.db.execute(
            self._with_user_relationships(select(AppUser).order_by(AppUser.username))
        )
        return list(result.scalars().all())

    async def get_user(self, username: str) -> AppUser | None:
        result = await self.db.execute(
            self._with_user_relationships(
                select(AppUser).where(AppUser.username == username)
            )
        )
        return result.scalar_one_or_none()

    async def get_user_by_sub(self, sub: str) -> AppUser | None:
        return await self._load_user_with_relationships(sub)

    async def get_user_by_identity(
        self, provider: str, provider_subject: str
    ) -> AppUser | None:
        stmt = self._with_user_relationships(
            select(AppUser)
            .join(UserIdentity, UserIdentity.user_sub == AppUser.sub)
            .where(
                UserIdentity.provider == provider,
                UserIdentity.provider_subject == provider_subject,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_local_user(
        self,
        *,
        username: str,
        password: str,
        email: str | None = None,
        display_name: str | None = None,
        is_admin: bool = False,
        is_disabled: bool = False,
        group_slugs: Iterable[str] = (),
    ) -> AppUser:
        from config import get_settings

        validate_local_password(password, get_settings())
        resolved_username = await self._require_available_username(username)
        now = utc_now()
        app_user = AppUser(
            sub=self._new_app_sub(),
            username=resolved_username,
            email=_normalize_email(email),
            display_name=(display_name or resolved_username).strip()
            or resolved_username,
            auth_display_source=LOCAL_PROVIDER,
            is_admin=is_admin,
            is_disabled=is_disabled,
            session_version=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.db.add(app_user)
        await self.db.flush()
        await self.set_password(
            app_user.sub,
            password,
            must_change_password=False,
            commit=False,
        )
        await self._replace_group_memberships(
            user_sub=app_user.sub,
            group_slugs=group_slugs,
            source=MANUAL_GROUP_SOURCE,
        )
        await self.db.commit()
        return await self._load_user_with_relationships(app_user.sub) or app_user

    async def update_user(
        self,
        *,
        user_sub: str,
        username: str | None = None,
        email: str | None = None,
        display_name: str | None = None,
        is_admin: bool | None = None,
        is_disabled: bool | None = None,
        group_slugs: Iterable[str] | None = None,
    ) -> AppUser | None:
        user = await self._load_user_with_relationships(user_sub)
        if user is None:
            return None

        if username is not None:
            user.username = await self._require_available_username(
                username,
                exclude_sub=user.sub,
            )
        if email is not None:
            user.email = _normalize_email(email)
        if display_name is not None:
            user.display_name = display_name.strip() or user.username
        if is_admin is not None:
            user.is_admin = is_admin
        if is_disabled is not None and user.is_disabled != is_disabled:
            user.is_disabled = is_disabled
            user.session_version = (user.session_version or 1) + 1
        user.last_seen_at = utc_now()

        if group_slugs is not None:
            await self._replace_group_memberships(
                user_sub=user.sub,
                group_slugs=group_slugs,
                source=MANUAL_GROUP_SOURCE,
            )

        await self.db.commit()
        return await self._load_user_with_relationships(user.sub)

    async def set_admin(self, username: str, is_admin: bool) -> bool:
        result = await self.db.execute(
            update(AppUser)
            .where(AppUser.username == username)
            .values(is_admin=is_admin)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def set_password(
        self,
        user_sub: str,
        raw_password: str,
        *,
        must_change_password: bool = False,
        commit: bool = True,
    ) -> None:
        from config import get_settings

        validate_local_password(raw_password, get_settings())
        user = await self._load_user_with_relationships(user_sub)
        if user is None:
            raise ValueError("Unknown user")

        hashed = _password_hasher.hash(raw_password)
        now = utc_now()
        credential = user.local_credentials
        if credential is None:
            self.db.add(
                LocalCredential(
                    user_sub=user_sub,
                    password_hash=hashed,
                    password_changed_at=now,
                    must_change_password=must_change_password,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            credential.password_hash = hashed
            credential.password_changed_at = now
            credential.must_change_password = must_change_password
            credential.updated_at = now

        identity = next(
            (item for item in user.identities if item.provider == LOCAL_PROVIDER),
            None,
        )
        if identity is None:
            self.db.add(
                UserIdentity(
                    provider=LOCAL_PROVIDER,
                    provider_subject=user.username,
                    user_sub=user.sub,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        user.auth_display_source = LOCAL_PROVIDER
        user.session_version = (user.session_version or 1) + 1
        user.last_seen_at = now
        if commit:
            await self.db.commit()

    async def change_password(
        self,
        *,
        user_sub: str,
        current_password: str,
        new_password: str,
    ) -> bool:
        user = await self._load_user_with_relationships(user_sub)
        if user is None or user.local_credentials is None:
            return False
        if not _password_hasher.verify(
            current_password,
            user.local_credentials.password_hash,
        ):
            return False
        await self.set_password(user_sub, new_password, commit=True)
        return True

    async def authenticate_local(
        self, *, identifier: str, password: str
    ) -> User | None:
        normalized_email = _normalize_email(identifier)
        conditions = [AppUser.username == identifier.strip()]
        if normalized_email:
            conditions.append(AppUser.email == normalized_email)

        stmt = self._with_user_relationships(
            select(AppUser)
            .join(LocalCredential, LocalCredential.user_sub == AppUser.sub)
            .where(or_(*conditions))
        ).limit(1)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None or user.local_credentials is None or user.is_disabled:
            return None
        if not _password_hasher.verify(password, user.local_credentials.password_hash):
            return None

        user.last_seen_at = utc_now()
        await self.db.commit()
        return await self._to_user_context(user, auth_provider=LOCAL_PROVIDER)

    async def ensure_proxy_user(
        self,
        *,
        provider_subject: str,
        username: str,
        email: str | None,
        display_name: str | None,
        external_groups: Iterable[str],
        preferred_username: str | None = None,
        uid: int | None = None,
        gids: list[int] | None = None,
        is_admin: bool = False,
    ) -> User:
        identity_stmt = (
            select(UserIdentity)
            .where(
                UserIdentity.provider == PROXY_PROVIDER,
                UserIdentity.provider_subject == provider_subject,
            )
            .options(selectinload(UserIdentity.user))
        )
        identity_result = await self.db.execute(identity_stmt)
        identity = identity_result.scalar_one_or_none()
        now = utc_now()
        normalized_groups = _normalize_group_values(external_groups)

        if identity is None:
            canonical_username = await self._dedupe_username(username)
            app_user = AppUser(
                sub=self._new_app_sub(),
                username=canonical_username,
                email=_normalize_email(email),
                display_name=(display_name or canonical_username).strip()
                or canonical_username,
                auth_display_source=PROXY_PROVIDER,
                is_admin=is_admin,
                is_disabled=False,
                session_version=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            self.db.add(app_user)
            await self.db.flush()
            identity = UserIdentity(
                provider=PROXY_PROVIDER,
                provider_subject=provider_subject,
                user_sub=app_user.sub,
                last_external_groups=normalized_groups or None,
                first_seen_at=now,
                last_seen_at=now,
            )
            self.db.add(identity)
        else:
            existing_user = await self._load_user_with_relationships(identity.user_sub)
            if existing_user is None:
                raise ValueError("Linked proxy user missing")
            app_user = existing_user
            app_user.username = await self._dedupe_username(
                username,
                exclude_sub=app_user.sub,
            )
            app_user.email = _normalize_email(email)
            app_user.display_name = (
                display_name or app_user.username
            ).strip() or app_user.username
            app_user.auth_display_source = PROXY_PROVIDER
            app_user.is_admin = is_admin
            app_user.last_seen_at = now
            identity.last_external_groups = normalized_groups or None
            identity.last_seen_at = now

        await self.sync_proxy_memberships(
            user_sub=identity.user_sub,
            external_groups=normalized_groups,
        )
        await self.db.commit()

        resolved_user = await self._load_user_with_relationships(identity.user_sub)
        if resolved_user is None:
            raise ValueError("Resolved proxy user missing")
        return await self._to_user_context(
            resolved_user,
            auth_provider=PROXY_PROVIDER,
            preferred_username=preferred_username,
            uid=uid,
            gids=gids,
        )

    async def ensure_dev_user(
        self,
        *,
        provider_subject: str,
        username: str,
        email: str | None,
        groups: Iterable[str],
    ) -> User:
        user = await self.get_user_by_identity(DEV_PROVIDER, provider_subject)
        now = utc_now()
        if user is None:
            user = AppUser(
                sub=provider_subject,
                username=await self._dedupe_username(username),
                email=_normalize_email(email),
                display_name=username,
                auth_display_source=DEV_PROVIDER,
                is_admin=True,
                is_disabled=False,
                session_version=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            self.db.add(user)
            await self.db.flush()
            self.db.add(
                UserIdentity(
                    provider=DEV_PROVIDER,
                    provider_subject=provider_subject,
                    user_sub=user.sub,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            user.is_admin = True
            user.is_disabled = False
            user.last_seen_at = now

        await self._replace_group_memberships(
            user_sub=user.sub,
            group_slugs=groups,
            source=MANUAL_GROUP_SOURCE,
        )
        await self.db.commit()
        resolved = await self._load_user_with_relationships(user.sub)
        if resolved is None:
            raise ValueError("Resolved dev user missing")
        return await self._to_user_context(resolved, auth_provider=DEV_PROVIDER)

    async def bootstrap_local_admin(self, settings) -> AppUser | None:
        result = await self.db.execute(
            select(AppUser.sub)
            .join(UserIdentity, UserIdentity.user_sub == AppUser.sub)
            .where(
                UserIdentity.provider == LOCAL_PROVIDER,
                AppUser.is_admin.is_(True),
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return None

        username = settings.AUTH_BOOTSTRAP_ADMIN_USERNAME.strip()
        password = settings.AUTH_BOOTSTRAP_ADMIN_PASSWORD
        if not username or not password:
            raise RuntimeError(
                "AUTH_LOCAL_ENABLED requires AUTH_BOOTSTRAP_ADMIN_USERNAME and "
                "AUTH_BOOTSTRAP_ADMIN_PASSWORD until a local admin exists."
            )

        try:
            return await self.create_local_user(
                username=username,
                password=password,
                email=settings.AUTH_BOOTSTRAP_ADMIN_EMAIL or None,
                display_name=settings.AUTH_BOOTSTRAP_ADMIN_DISPLAY_NAME or username,
                is_admin=True,
                is_disabled=False,
            )
        except PasswordPolicyError as exc:
            raise RuntimeError(
                "AUTH_BOOTSTRAP_ADMIN_PASSWORD does not meet local password policy: "
                f"{exc}"
            ) from exc
