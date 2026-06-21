"""Backend-managed permission service (folder-level only)."""

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.sqlalchemy_models import IndexedContentItem, Permission, utc_now


class PermissionService:
    """CRUD and evaluation of folder permissions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _permission_stmt(folder_uuid: str, trustee: str):
        return select(Permission).where(
            Permission.folder_uuid == folder_uuid,
            Permission.trustee == trustee,
        )

    async def get_permissions(self, folder_uuid: str) -> list[Permission]:
        """Get all permission entries for a folder."""
        stmt = select(Permission).where(
            Permission.folder_uuid == folder_uuid,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def set_permission(
        self,
        folder_uuid: str,
        trustee: str,
        access: str = "allow",
        granted_by: str | None = None,
    ) -> Permission:
        """Add or update a permission entry."""
        result = await self.db.execute(self._permission_stmt(folder_uuid, trustee))
        existing = result.scalar_one_or_none()

        now = utc_now()
        if existing is None:
            existing = Permission(
                folder_uuid=folder_uuid,
                trustee=trustee,
                access=access,
                granted_by=granted_by,
                created_at=now,
            )
            self.db.add(existing)
        else:
            existing.access = access
            existing.granted_by = granted_by
            existing.created_at = now

        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    async def remove_permission(self, folder_uuid: str, trustee: str) -> bool:
        """Remove a permission entry. Returns True if a row was deleted."""
        stmt = delete(Permission).where(
            Permission.folder_uuid == folder_uuid,
            Permission.trustee == trustee,
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def compute_effective_viewers(
        self, folder_uuid: str
    ) -> tuple[list[str], list[str]]:
        """Compute (allowed_viewers, denied_viewers) for a folder."""
        folder_perms = await self.get_permissions(folder_uuid)
        if not folder_perms:
            return [], []
        return self._split_permissions(folder_perms)

    async def propagate_folder_permissions(self, folder_uuid: str) -> int:
        """Update ACL lists on all IndexedContentItem records in a folder."""
        allowed, denied = await self.compute_effective_viewers(folder_uuid)
        allowed_viewers = allowed or None
        denied_viewers = denied or None

        stmt = (
            update(IndexedContentItem)
            .where(IndexedContentItem.folder_uuid == folder_uuid)
            .values(
                allowed_viewers=allowed_viewers,
                denied_viewers=denied_viewers,
            )
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    @staticmethod
    def _split_permissions(
        perms: list[Permission],
    ) -> tuple[list[str], list[str]]:
        """Split a list of Permission rows into (allowed, denied) trustee lists."""
        allowed: list[str] = []
        denied: list[str] = []
        for p in perms:
            if p.access == "deny":
                denied.append(p.trustee)
            else:
                allowed.append(p.trustee)
        return allowed, denied
