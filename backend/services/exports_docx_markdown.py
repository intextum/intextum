"""Markdown normalization helpers for DOCX export."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET_PATTERN = re.compile(r"^\s*[-*]\s+(.*)$")
_NUMBERED_PATTERN = re.compile(r"^\s*(\d+)\.\s+(.*)$")
_IMAGE_LINE_PATTERN = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_INLINE_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_INLINE_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
_EMPHASIS_PATTERNS = [
    re.compile(r"\*\*(.+?)\*\*"),
    re.compile(r"__(.+?)__"),
    re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)"),
    re.compile(r"(?<!_)_(?!\s)(.+?)(?<!\s)_(?!_)"),
]


@dataclass(frozen=True)
class _DocxParagraph:
    kind: str
    text: str
    image_url: str | None = None
    table_rows: tuple[tuple[str, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _DocxInlineRun:
    text: str
    hyperlink_url: str | None = None


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    stripped = re.sub(r"^```(?:[a-zA-Z0-9_-]+)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _normalize_inline_markdown_for_runs(text: str) -> str:
    normalized = text.replace("\\[", "[").replace("\\]", "]")

    token_replacements: dict[str, str] = {}

    def replace_image(match: re.Match[str]) -> str:
        placeholder = f"\u0000img{len(token_replacements)}\u0000"
        token_replacements[placeholder] = (
            f"{(match.group(1) or 'Image').strip() or 'Image'} ({match.group(2).strip()})"
        )
        return placeholder

    def replace_link(match: re.Match[str]) -> str:
        placeholder = f"\u0000lnk{len(token_replacements)}\u0000"
        token_replacements[placeholder] = match.group(0)
        return placeholder

    normalized = _INLINE_IMAGE_PATTERN.sub(replace_image, normalized)
    normalized = _INLINE_LINK_PATTERN.sub(replace_link, normalized)
    normalized = _INLINE_CODE_PATTERN.sub(lambda match: match.group(1), normalized)
    for pattern in _EMPHASIS_PATTERNS:
        normalized = pattern.sub(lambda match: match.group(1), normalized)
    for placeholder, replacement in token_replacements.items():
        normalized = normalized.replace(placeholder, replacement)
    return normalized.strip()


def _flatten_inline_markdown(text: str) -> str:
    normalized = _normalize_inline_markdown_for_runs(text)
    flattened = _INLINE_LINK_PATTERN.sub(
        lambda match: f"{match.group(1).strip()} ({match.group(2).strip()})",
        normalized,
    )
    return flattened.strip()


def _split_markdown_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if "|" not in stripped:
        return None

    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())

    if len(cells) < 2:
        return None
    return [_normalize_inline_markdown_for_runs(cell) for cell in cells]


def _is_markdown_table_separator(cells: list[str] | None) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _inline_runs(text: str) -> list[_DocxInlineRun]:
    normalized = _normalize_inline_markdown_for_runs(text)
    if not normalized:
        return []

    runs: list[_DocxInlineRun] = []
    cursor = 0
    for match in _INLINE_LINK_PATTERN.finditer(normalized):
        if match.start() > cursor:
            runs.append(_DocxInlineRun(text=normalized[cursor : match.start()]))
        runs.append(
            _DocxInlineRun(
                text=match.group(1),
                hyperlink_url=match.group(2).strip(),
            )
        )
        cursor = match.end()

    if cursor < len(normalized):
        runs.append(_DocxInlineRun(text=normalized[cursor:]))

    return [run for run in runs if run.text]


def _markdown_to_docx_paragraphs(markdown: str, *, title: str) -> list[_DocxParagraph]:
    paragraphs: list[_DocxParagraph] = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraphs.append(
            _DocxParagraph(
                kind="paragraph",
                text=_normalize_inline_markdown_for_runs(
                    " ".join(line.strip() for line in paragraph_lines)
                ),
            )
        )
        paragraph_lines.clear()

    def flush_code_block() -> None:
        if not code_lines:
            return
        for line in code_lines:
            paragraphs.append(
                _DocxParagraph(kind="code", text=_strip_code_fences(line.rstrip("\n")))
            )
        code_lines.clear()

    has_explicit_title = False
    lines = markdown.replace("\r\n", "\n").split("\n")
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            if in_code_block:
                flush_code_block()
            in_code_block = not in_code_block
            index += 1
            continue

        if in_code_block:
            code_lines.append(raw_line)
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if stripped == "---":
            flush_paragraph()
            index += 1
            continue

        table_header = _split_markdown_table_row(stripped)
        next_table_separator = (
            _split_markdown_table_row(lines[index + 1].strip())
            if index + 1 < len(lines)
            else None
        )
        if table_header and _is_markdown_table_separator(next_table_separator):
            flush_paragraph()
            table_rows = [table_header]
            index += 2
            while index < len(lines):
                row_cells = _split_markdown_table_row(lines[index].strip())
                if not row_cells or _is_markdown_table_separator(row_cells):
                    break
                table_rows.append(row_cells)
                index += 1
            max_columns = max(len(row) for row in table_rows)
            paragraphs.append(
                _DocxParagraph(
                    kind="table",
                    text="",
                    table_rows=tuple(
                        tuple([*row, *([""] * (max_columns - len(row)))])
                        for row in table_rows
                    ),
                )
            )
            continue

        if stripped.startswith("> "):
            flush_paragraph()
            paragraphs.append(
                _DocxParagraph(
                    kind="quote",
                    text=_normalize_inline_markdown_for_runs(stripped[2:]),
                )
            )
            index += 1
            continue

        image_match = _IMAGE_LINE_PATTERN.match(stripped)
        if image_match:
            flush_paragraph()
            alt_text = _flatten_inline_markdown(image_match.group(1).strip()) or "Image"
            paragraphs.append(
                _DocxParagraph(
                    kind="image",
                    text=alt_text,
                    image_url=image_match.group(2).strip(),
                )
            )
            index += 1
            continue

        heading_match = _HEADING_PATTERN.match(stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            heading_text = _normalize_inline_markdown_for_runs(heading_match.group(2))
            paragraphs.append(_DocxParagraph(kind=f"heading{level}", text=heading_text))
            if level == 1:
                has_explicit_title = True
            index += 1
            continue

        bullet_match = _BULLET_PATTERN.match(stripped)
        if bullet_match:
            flush_paragraph()
            paragraphs.append(
                _DocxParagraph(
                    kind="bullet",
                    text=f"• {_normalize_inline_markdown_for_runs(bullet_match.group(1))}",
                )
            )
            index += 1
            continue

        numbered_match = _NUMBERED_PATTERN.match(stripped)
        if numbered_match:
            flush_paragraph()
            paragraphs.append(
                _DocxParagraph(
                    kind="numbered",
                    text=(
                        f"{numbered_match.group(1)}. "
                        f"{_normalize_inline_markdown_for_runs(numbered_match.group(2))}"
                    ),
                )
            )
            index += 1
            continue

        paragraph_lines.append(raw_line)
        index += 1

    flush_paragraph()
    flush_code_block()

    if not has_explicit_title:
        return [_DocxParagraph(kind="heading1", text=title), *paragraphs]
    return paragraphs
