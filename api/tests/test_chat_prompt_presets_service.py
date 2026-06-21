"""Tests for configurable chat prompt preset service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.chat.prompt_presets import PromptPresetInput, validate_prompt_preset_list
from models.sqlalchemy_models import AppSetting
from services.chat_prompt_presets import (
    CHAT_PROMPT_PRESETS_SETTING_KEY,
    ChatPromptPresetService,
)


def _db_with_row(row: AppSetting | None = None) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db.execute.return_value = result
    db.add = MagicMock()
    return db


def _preset(**overrides) -> PromptPresetInput:
    data = {
        "id": "demo",
        "enabled": True,
        "sort_order": 10,
        "mode": "chat",
        "label": {"en": "Demo", "de": "Demo"},
        "description": {"en": "Demo preset", "de": "Demo Preset"},
        "prompt": {"en": "Summarize this.", "de": "Fasse dies zusammen."},
        "icon": "sparkles",
        "context": {"min_files": 1, "max_files": 2},
        "action": "fill",
    }
    data.update(overrides)
    return PromptPresetInput.model_validate(data)


@pytest.mark.asyncio
async def test_get_presets_returns_enabled_sorted_defaults():
    response = await ChatPromptPresetService(_db_with_row()).get_presets()

    assert len(response.presets) >= 6
    assert all(preset.enabled for preset in response.presets)
    assert [preset.sort_order for preset in response.presets] == sorted(
        preset.sort_order for preset in response.presets
    )
    assert any(
        preset.mode == "research" and preset.context.max_files == 1
        for preset in response.presets
    )


@pytest.mark.asyncio
async def test_get_presets_filters_disabled_database_presets():
    row = AppSetting(
        key=CHAT_PROMPT_PRESETS_SETTING_KEY,
        value_json=[
            _preset(id="enabled", enabled=True).model_dump(mode="json"),
            _preset(id="disabled", enabled=False).model_dump(mode="json"),
        ],
    )

    response = await ChatPromptPresetService(_db_with_row(row)).get_presets()

    assert [preset.id for preset in response.presets] == ["enabled"]


@pytest.mark.asyncio
async def test_replace_presets_upserts_app_setting():
    db = _db_with_row()

    response = await ChatPromptPresetService(db).replace_presets(
        [_preset()],
        updated_by="admin",
    )

    assert [preset.id for preset in response.presets] == ["demo"]
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert isinstance(added, AppSetting)
    assert added.key == CHAT_PROMPT_PRESETS_SETTING_KEY
    assert added.value_json[0]["id"] == "demo"
    assert added.updated_by == "admin"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_presets_deletes_override_and_returns_defaults():
    row = AppSetting(key=CHAT_PROMPT_PRESETS_SETTING_KEY, value_json=[])
    db = _db_with_row(row)

    response = await ChatPromptPresetService(db).reset_presets()

    db.delete.assert_awaited_once_with(row)
    db.commit.assert_awaited_once()
    assert len(response.presets) >= 6


def test_validate_prompt_preset_list_rejects_duplicate_ids():
    payload = [
        _preset(id="duplicate").model_dump(mode="json"),
        _preset(id="duplicate").model_dump(mode="json"),
    ]

    with pytest.raises(ValueError, match="duplicate_prompt_preset_ids"):
        validate_prompt_preset_list(payload)


def test_prompt_preset_requires_valid_context_range():
    with pytest.raises(ValueError, match="max_files_must"):
        _preset(context={"min_files": 3, "max_files": 2})


def test_prompt_preset_accepts_single_language_english():
    preset = _preset(
        label={"en": "Only English"},
        description={"en": "English description"},
        prompt={"en": "Run this prompt."},
    )

    assert preset.label == {"en": "Only English"}
    assert preset.description == {"en": "English description"}
    assert preset.prompt == {"en": "Run this prompt."}


def test_prompt_preset_accepts_single_language_german():
    preset = _preset(
        label={"de": "Nur Deutsch"},
        description={"de": "Deutsche Beschreibung"},
        prompt={"de": "Fuhre diesen Prompt aus."},
    )

    assert preset.label == {"de": "Nur Deutsch"}
    assert preset.description == {"de": "Deutsche Beschreibung"}
    assert preset.prompt == {"de": "Fuhre diesen Prompt aus."}


def test_prompt_preset_requires_at_least_one_complete_locale():
    with pytest.raises(ValueError, match="at_least_one_complete_locale"):
        _preset(label={}, description={}, prompt={})


def test_prompt_preset_rejects_partially_filled_locale():
    with pytest.raises(
        ValueError, match="de_locale_requires_label_description_and_prompt"
    ):
        _preset(
            label={"en": "English", "de": "Deutsch"},
            description={"en": "English description"},
            prompt={"en": "Run this prompt."},
        )
