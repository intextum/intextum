"""Context path resolution helpers for request-scoped chat runtime."""

import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import unquote

from chat.documents import resolve_document_path
from services.connector import ConnectorRuntimeService
from services.utils import compute_content_item_id

logger = logging.getLogger(__name__)

ContextConstraint = tuple[str, str, str]


def normalize_api_path(path: str) -> str:
    """Normalize a user-supplied API path to a stable slash-separated form."""
    unquoted = unquote(path)
    if any(ord(char) < 32 for char in unquoted):
        return ""

    normalized = str(PurePosixPath(unquoted.replace("\\", "/").strip().strip("/")))
    if normalized in {"", "."}:
        return ""

    if any(part == ".." for part in normalized.split("/")):
        return ""

    return unicodedata.normalize("NFC", normalized)


@dataclass(frozen=True)
class ChatContextScope:
    """Resolved request-scoped context selection for chat tools and prompting."""

    raw_paths: list[str] = field(default_factory=list)
    constraints: list[ContextConstraint] = field(default_factory=list)
    folder_name_to_uuid: dict[str, str] = field(default_factory=dict)
    folder_uuid_to_name: dict[str, str] = field(default_factory=dict)
    file_ids: list[str] = field(default_factory=list)
    allowed_pairs: frozenset[tuple[str, str]] = field(default_factory=frozenset)

    @property
    def has_selection(self) -> bool:
        """Return whether the user selected any context files at all."""
        return bool(self.raw_paths)

    @property
    def has_constraints(self) -> bool:
        """Return whether any selected files resolved to valid source entries."""
        return bool(self.constraints)

    @property
    def folder_names(self) -> set[str]:
        """Return the configured top-level data folder names."""
        return set(self.folder_name_to_uuid)

    def contains(self, folder_uuid: str, relative_path: str) -> bool:
        """Return whether one file falls within the resolved context scope."""
        return (folder_uuid, relative_path) in self.allowed_pairs


def build_context_scope(context_file_paths: list[str]) -> ChatContextScope:
    """Resolve selected context paths once per request."""
    folder_name_to_uuid, folder_uuid_to_name = (
        ConnectorRuntimeService().connector_name_maps(browsable_only=True)
    )

    constraints: list[ContextConstraint] = []
    seen_pairs: set[tuple[str, str]] = set()
    for raw_path in context_file_paths:
        normalized_path = normalize_api_path(raw_path)
        if not normalized_path:
            continue

        try:
            folder_uuid, relative_path = resolve_document_path(
                normalized_path, folder_name_to_uuid
            )
        except ValueError:
            logger.warning("Ignoring invalid context file path.")
            continue

        key = (folder_uuid, relative_path)
        if key in seen_pairs:
            continue

        seen_pairs.add(key)
        constraints.append((normalized_path, folder_uuid, relative_path))

    return ChatContextScope(
        raw_paths=list(context_file_paths),
        constraints=constraints,
        folder_name_to_uuid=folder_name_to_uuid,
        folder_uuid_to_name=folder_uuid_to_name,
        file_ids=[
            compute_content_item_id(folder_uuid, relative_path)
            for _, folder_uuid, relative_path in constraints
        ],
        allowed_pairs=frozenset(
            (folder_uuid, relative_path)
            for _, folder_uuid, relative_path in constraints
        ),
    )


def _deduped_normalized_paths(raw_paths: list[str]) -> list[str]:
    candidates: list[str] = []
    seen_candidates: set[str] = set()
    for raw_path in raw_paths:
        normalized_candidate = normalize_api_path(raw_path)
        if normalized_candidate and normalized_candidate not in seen_candidates:
            candidates.append(normalized_candidate)
            seen_candidates.add(normalized_candidate)
    return candidates


def _document_target_candidates(
    context_scope: ChatContextScope,
    source_paths: list[str],
) -> list[str]:
    return _deduped_normalized_paths(
        [api_path for api_path, _, _ in context_scope.constraints] + source_paths
    )


def _matching_document_targets(
    normalized_input: str,
    candidates: list[str],
) -> list[str]:
    if "/" in normalized_input:
        return [
            candidate
            for candidate in candidates
            if candidate == normalized_input
            or candidate.endswith(f"/{normalized_input}")
        ]

    return [
        candidate
        for candidate in candidates
        if candidate.split("/")[-1] == normalized_input
    ]


def _ambiguous_document_path_error(matches: list[str]) -> str:
    options = ", ".join(sorted(matches)[:5])
    return (
        "Ambiguous document path. Use the full path including folder name. "
        f"Possible matches: {options}"
    )


def resolve_get_document_target_path(
    *,
    raw_file_path: str,
    context_scope: ChatContextScope,
    source_paths: list[str],
) -> tuple[str | None, str | None]:
    """Resolve get_document input to a canonical API path when possible."""
    normalized_input = normalize_api_path(raw_file_path)
    if not normalized_input:
        return None, "Document path is empty."

    first_segment, _, remainder = normalized_input.partition("/")
    if first_segment in context_scope.folder_names and remainder:
        return normalized_input, None

    candidates = _document_target_candidates(context_scope, source_paths)
    if not candidates:
        return normalized_input, None

    matches = _matching_document_targets(normalized_input, candidates)
    if len(matches) == 1:
        return matches[0], None

    if len(matches) > 1:
        return None, _ambiguous_document_path_error(matches)

    return normalized_input, None
