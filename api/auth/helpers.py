"""Shared helpers for auth dependencies."""

from typing import List, Optional

from fastapi import HTTPException, status


def parse_groups_header(groups_header: str) -> List[str]:
    """Parse comma-separated groups header into normalized list."""
    return [group.strip() for group in groups_header.split(",") if group.strip()]


def parse_optional_int(value: Optional[str]) -> Optional[int]:
    """Parse an optional integer-like header value."""
    if value is None:
        return None
    parsed = value.strip()
    if not parsed:
        return None
    try:
        return int(parsed)
    except ValueError:
        return None


def parse_int_list_header(values_header: str) -> List[int]:
    """Parse comma-separated integer list header, ignoring invalid entries."""
    parsed: List[int] = []
    seen: set[int] = set()
    for token in values_header.split(","):
        value = parse_optional_int(token)
        if value is None or value in seen:
            continue
        seen.add(value)
        parsed.append(value)
    return parsed


def unauthorized(detail: str) -> HTTPException:
    """Build a 401 Unauthorized HTTPException."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def forbidden(detail: str) -> HTTPException:
    """Build a 403 Forbidden HTTPException."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
    )
