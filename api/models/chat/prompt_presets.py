"""Typed models for configurable chat and research prompt presets."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PromptPresetMode = Literal["chat", "research"]
PromptPresetAction = Literal["fill", "submit"]
PromptPresetIcon = Literal[
    "bar-chart",
    "book-open",
    "file-search",
    "file-text",
    "list-checks",
    "search",
    "sparkles",
]


class PromptPresetContextRequirement(BaseModel):
    """Selected-file requirements for one prompt preset."""

    min_files: int = Field(default=0, ge=0, le=100)
    max_files: int | None = Field(default=None, ge=0, le=100)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_range(self):
        if self.max_files is not None and self.max_files < self.min_files:
            raise ValueError("max_files_must_be_greater_than_or_equal_to_min_files")
        return self


class PromptPresetInput(BaseModel):
    """Admin-editable prompt preset."""

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    enabled: bool = True
    sort_order: int = Field(default=100, ge=0, le=100_000)
    mode: PromptPresetMode = "chat"
    label: dict[str, str] = Field(default_factory=dict)
    description: dict[str, str] = Field(default_factory=dict)
    prompt: dict[str, str] = Field(default_factory=dict)
    icon: PromptPresetIcon = "sparkles"
    context: PromptPresetContextRequirement = Field(
        default_factory=PromptPresetContextRequirement
    )
    action: PromptPresetAction = "fill"

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @staticmethod
    def _normalize_localized_text(value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for locale, text in value.items():
            locale_key = locale.strip().lower()
            if not locale_key:
                continue
            trimmed = text.strip()
            if trimmed:
                normalized[locale_key] = trimmed
        return normalized

    @model_validator(mode="after")
    def _validate_localized_text(self):
        self.label = self._normalize_localized_text(self.label)
        self.description = self._normalize_localized_text(self.description)
        self.prompt = self._normalize_localized_text(self.prompt)

        locales = set(self.label) | set(self.description) | set(self.prompt)
        complete_locales: set[str] = set()
        for locale in locales:
            has_label = bool(self.label.get(locale))
            has_description = bool(self.description.get(locale))
            has_prompt = bool(self.prompt.get(locale))
            if has_label and has_description and has_prompt:
                complete_locales.add(locale)
                continue
            raise ValueError(f"{locale}_locale_requires_label_description_and_prompt")

        if not complete_locales:
            raise ValueError("prompt_preset_requires_at_least_one_complete_locale")
        return self


class PromptPreset(PromptPresetInput):
    """Validated prompt preset returned by APIs."""


class PromptPresetListResponse(BaseModel):
    """Prompt preset collection response."""

    presets: list[PromptPreset] = Field(default_factory=list)


class PromptPresetUpdateRequest(BaseModel):
    """Admin request replacing all prompt presets."""

    presets: list[PromptPresetInput] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def validate_prompt_preset_list(raw_presets: Any) -> list[PromptPreset]:
    """Validate one raw preset list and reject duplicate ids."""
    if not isinstance(raw_presets, list):
        raise ValueError("prompt_presets_must_be_a_list")

    presets = [PromptPreset.model_validate(item) for item in raw_presets]
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for preset in presets:
        if preset.id in seen_ids:
            duplicate_ids.add(preset.id)
        seen_ids.add(preset.id)
    if duplicate_ids:
        raise ValueError(
            f"duplicate_prompt_preset_ids: {', '.join(sorted(duplicate_ids))}"
        )

    def sort_label(preset: PromptPreset) -> str:
        return preset.label.get("en") or next(iter(preset.label.values()), "")

    return sorted(
        presets, key=lambda item: (item.sort_order, sort_label(item), item.id)
    )
