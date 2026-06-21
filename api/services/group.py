"""Group and proxy-alias management services."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.sqlalchemy_models import Group, GroupExternalAlias, GroupMembership, utc_now


class DuplicateGroupAliasError(ValueError):
    """Raised when a proxy alias is already assigned to another group."""


def normalize_group_slug(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    if not normalized:
        raise ValueError("group slug must not be empty")
    return normalized


def normalize_external_alias(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("external alias must not be empty")
    return normalized


class GroupService:
    """CRUD for app-managed groups and proxy alias mappings."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _with_group_relationships(stmt):
        return stmt.options(
            selectinload(Group.external_aliases),
            selectinload(Group.memberships),
        )

    async def list_groups(self) -> list[Group]:
        result = await self.db.execute(
            self._with_group_relationships(select(Group).order_by(Group.slug))
        )
        return list(result.scalars().all())

    async def get_group(self, slug: str) -> Group | None:
        result = await self.db.execute(
            self._with_group_relationships(
                select(Group).where(Group.slug == normalize_group_slug(slug))
            )
        )
        return result.scalar_one_or_none()

    async def create_group(
        self,
        *,
        slug: str,
        display_name: str,
        description: str | None = None,
        proxy_aliases: Iterable[str] = (),
    ) -> Group:
        normalized_slug = normalize_group_slug(slug)
        group = Group(
            slug=normalized_slug,
            display_name=display_name.strip() or normalized_slug,
            description=description,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.db.add(group)
        await self.db.flush()
        await self.replace_proxy_aliases(normalized_slug, proxy_aliases, commit=False)
        await self.db.commit()
        return await self.get_group(normalized_slug) or group

    async def update_group(
        self,
        *,
        slug: str,
        display_name: str | None = None,
        description: str | None = None,
        proxy_aliases: Iterable[str] | None = None,
    ) -> Group | None:
        group = await self.get_group(slug)
        if group is None:
            return None
        if display_name is not None:
            group.display_name = display_name.strip() or group.slug
        if description is not None:
            group.description = description
        group.updated_at = utc_now()
        if proxy_aliases is not None:
            await self.replace_proxy_aliases(group.slug, proxy_aliases, commit=False)
        await self.db.commit()
        return await self.get_group(group.slug)

    async def delete_group(self, slug: str) -> bool:
        result = await self.db.execute(
            delete(Group).where(Group.slug == normalize_group_slug(slug))
        )
        await self.db.commit()
        return result.rowcount > 0

    async def replace_proxy_aliases(
        self,
        group_slug: str,
        proxy_aliases: Iterable[str],
        *,
        commit: bool = True,
    ) -> None:
        normalized_slug = normalize_group_slug(group_slug)
        normalized_aliases = list(
            dict.fromkeys(normalize_external_alias(alias) for alias in proxy_aliases)
        )
        if normalized_aliases:
            existing = await self.db.execute(
                select(GroupExternalAlias)
                .where(
                    GroupExternalAlias.provider == "proxy",
                    GroupExternalAlias.external_value.in_(normalized_aliases),
                    GroupExternalAlias.group_slug != normalized_slug,
                )
                .limit(1)
            )
            conflict = existing.scalar_one_or_none()
            if conflict is not None:
                raise DuplicateGroupAliasError(
                    f"Proxy alias '{conflict.external_value}' is already assigned"
                )

        await self.db.execute(
            delete(GroupExternalAlias).where(
                GroupExternalAlias.group_slug == normalized_slug,
                GroupExternalAlias.provider == "proxy",
            )
        )
        for normalized_alias in normalized_aliases:
            self.db.add(
                GroupExternalAlias(
                    group_slug=normalized_slug,
                    provider="proxy",
                    external_value=normalized_alias,
                )
            )
        if commit:
            await self.db.commit()

    async def member_count(self, slug: str) -> int:
        result = await self.db.execute(
            select(func.count(GroupMembership.id)).where(
                GroupMembership.group_slug == normalize_group_slug(slug)
            )
        )
        return int(result.scalar_one() or 0)
