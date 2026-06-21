"""Path navigation helpers for flat file stats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User

from .filters import FlatContentListFilters


class FlatContentPathServiceProtocol(Protocol):
    """Internal ContentStatsService surface used by path helpers."""

    db: AsyncSession

    @staticmethod
    def _flat_file_base_stmt(): ...

    @staticmethod
    def _apply_flat_filters(stmt, *, filters: FlatContentListFilters): ...

    @staticmethod
    def _apply_flat_sort(stmt, *, sort_by: str, sort_order: str): ...


@dataclass(slots=True)
class FlatContentPathNavigator:
    """Build matching file paths from one filter state."""

    service: FlatContentPathServiceProtocol
    user: User | None
    flat_filters: FlatContentListFilters
    folder_resolver: Callable[[str], Any | None]

    def _filtered_base(self):
        return self.service._apply_flat_filters(
            self.service._flat_file_base_stmt(),
            filters=self.flat_filters,
        )

    @staticmethod
    def _format_path(folder, relative_path: str | None) -> str:
        """Format one folder-prefixed API path."""
        return f"{folder.name}/{relative_path}" if relative_path else folder.name

    async def list_matching_paths(self) -> list[str]:
        """Return all matching folder-prefixed API paths in name order."""
        stmt = self.service._apply_flat_sort(
            self._filtered_base(),
            sort_by="name",
            sort_order="asc",
        )
        rows = (await self.service.db.execute(stmt)).scalars().all()

        paths: list[str] = []
        for row in rows:
            folder = self.folder_resolver(row.folder_uuid)
            if folder is not None:
                paths.append(self._format_path(folder, row.relative_path))
        return paths
