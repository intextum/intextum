"""Service for admin-managed chat and deep research prompt presets."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.chat.prompt_presets import (
    PromptPreset,
    PromptPresetListResponse,
    PromptPresetInput,
    validate_prompt_preset_list,
)
from models.sqlalchemy_models import AppSetting

CHAT_PROMPT_PRESETS_SETTING_KEY = "chat_prompt_presets"


DEFAULT_CHAT_PROMPT_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "id": "summarize_documents",
        "enabled": True,
        "sort_order": 10,
        "mode": "chat",
        "label": {
            "en": "Summarize documents",
            "de": "Dokumente zusammenfassen",
        },
        "description": {
            "en": "Create a concise summary of the selected document context.",
            "de": "Erstellt eine kurze Zusammenfassung des ausgewählten Dokumentkontexts.",
        },
        "prompt": {
            "en": "Summarize the selected document(s). If multiple documents are selected, provide a per-document summary followed by a concise overall summary.",
            "de": "Fasse die ausgewählten Dokumente zusammen. Wenn mehrere Dokumente ausgewählt sind, erstelle zuerst Zusammenfassungen pro Dokument und danach eine kurze Gesamtsynthese.",
        },
        "icon": "file-text",
        "context": {"min_files": 1},
        "action": "fill",
    },
    {
        "id": "compare_documents",
        "enabled": True,
        "sort_order": 20,
        "mode": "chat",
        "label": {
            "en": "Compare documents",
            "de": "Dokumente vergleichen",
        },
        "description": {
            "en": "Compare two or more selected files and highlight contradictions.",
            "de": "Vergleicht zwei oder mehr Dateien und hebt Widersprüche hervor.",
        },
        "prompt": {
            "en": "Compare the selected documents. Highlight key similarities, differences, and notable contradictions. If more than two documents are selected, structure the comparison clearly by document.",
            "de": "Vergleiche die ausgewählten Dokumente. Hebe zentrale Gemeinsamkeiten, Unterschiede und mögliche Widersprüche hervor. Wenn mehr als zwei Dokumente ausgewählt sind, strukturiere den Vergleich klar pro Dokument.",
        },
        "icon": "bar-chart",
        "context": {"min_files": 2},
        "action": "fill",
    },
    {
        "id": "find_information",
        "enabled": True,
        "sort_order": 30,
        "mode": "chat",
        "label": {
            "en": "Find information",
            "de": "Informationen finden",
        },
        "description": {
            "en": "Search the accessible document collection for focused answers.",
            "de": "Sucht im zugänglichen Dokumentbestand nach gezielten Antworten.",
        },
        "prompt": {
            "en": "Find specific information relevant to my likely intent in the selected context. Return direct answers with short supporting citations and note uncertainty where evidence is weak.",
            "de": "Finde konkrete Informationen, die voraussichtlich zu meiner Absicht in den ausgewählten Kontextdateien passen. Gib direkte Antworten mit kurzen Quellenhinweisen und markiere Unsicherheiten bei schwacher Evidenz.",
        },
        "icon": "search",
        "context": {"min_files": 0},
        "action": "fill",
    },
    {
        "id": "extract_key_data",
        "enabled": True,
        "sort_order": 40,
        "mode": "chat",
        "label": {
            "en": "Extract key data",
            "de": "Kerndaten extrahieren",
        },
        "description": {
            "en": "Return structured values with source references and missing data.",
            "de": "Gibt strukturierte Werte mit Quellenhinweisen und fehlenden Daten zurück.",
        },
        "prompt": {
            "en": "Extract key data points from the selected context. Return a structured list with fields, values, source references, and missing data explicitly marked.",
            "de": "Extrahiere wichtige Datenpunkte aus dem ausgewählten Kontext. Gib eine strukturierte Liste mit Feld, Wert, Quellenhinweis und kennzeichne fehlende Daten explizit.",
        },
        "icon": "list-checks",
        "context": {"min_files": 0},
        "action": "fill",
    },
    {
        "id": "single_document_deep_extraction",
        "enabled": True,
        "sort_order": 50,
        "mode": "research",
        "label": {
            "en": "Deep extract one document",
            "de": "Ein Dokument tief extrahieren",
        },
        "description": {
            "en": "Use deep research over one selected file for complex cited extraction.",
            "de": "Nutzt Deep Research über eine ausgewählte Datei für komplexe belegte Extraktion.",
        },
        "prompt": {
            "en": "Extract the relevant obligations, tasks, dates, responsible parties, material types, identifiers, and open questions from the selected document. Produce a concise cited report with a structured table and note uncertain or missing values explicitly.",
            "de": "Extrahiere relevante Pflichten, Aufgaben, Fristen, Verantwortliche, Materialtypen, Kennungen und offene Fragen aus dem ausgewählten Dokument. Erstelle einen knappen Bericht mit Zitaten, strukturierter Tabelle und expliziten Hinweisen auf unsichere oder fehlende Werte.",
        },
        "icon": "file-search",
        "context": {"min_files": 1, "max_files": 1},
        "action": "fill",
    },
    {
        "id": "multi_document_research_comparison",
        "enabled": True,
        "sort_order": 60,
        "mode": "research",
        "label": {
            "en": "Research across documents",
            "de": "Dokumentübergreifend recherchieren",
        },
        "description": {
            "en": "Create a cited report comparing two or more selected files.",
            "de": "Erstellt einen belegten Bericht zum Vergleich von zwei oder mehr Dateien.",
        },
        "prompt": {
            "en": "Create a cited deep research report across the selected documents. Compare the key facts, obligations, dates, conflicts, and gaps. Use clear sections and include a concise summary table.",
            "de": "Erstelle einen belegten Deep-Research-Bericht über die ausgewählten Dokumente. Vergleiche zentrale Fakten, Pflichten, Fristen, Widersprüche und Lücken. Nutze klare Abschnitte und eine kurze Übersichtstabelle.",
        },
        "icon": "book-open",
        "context": {"min_files": 2},
        "action": "fill",
    },
)


def default_prompt_presets() -> list[PromptPreset]:
    """Return validated built-in prompt presets."""
    return validate_prompt_preset_list(list(DEFAULT_CHAT_PROMPT_PRESETS))


def _preset_payloads(presets: list[PromptPreset | PromptPresetInput]) -> list[dict]:
    return [preset.model_dump(mode="json") for preset in presets]


class ChatPromptPresetService:
    """Load and persist prompt presets stored as one AppSetting value."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_row(self) -> AppSetting | None:
        result = await self.db.execute(
            select(AppSetting).where(AppSetting.key == CHAT_PROMPT_PRESETS_SETTING_KEY)
        )
        return result.scalar_one_or_none()

    async def get_presets(
        self, *, include_disabled: bool = False
    ) -> PromptPresetListResponse:
        """Return configured presets or built-in defaults."""
        row = await self._load_row()
        presets = (
            default_prompt_presets()
            if row is None
            else validate_prompt_preset_list(row.value_json)
        )
        if not include_disabled:
            presets = [preset for preset in presets if preset.enabled]
        return PromptPresetListResponse(presets=presets)

    async def replace_presets(
        self,
        presets: list[PromptPresetInput],
        *,
        updated_by: str | None = None,
    ) -> PromptPresetListResponse:
        """Replace all stored prompt presets."""
        validated = validate_prompt_preset_list(_preset_payloads(presets))
        row = await self._load_row()
        value_json = _preset_payloads(validated)
        if row is None:
            self.db.add(
                AppSetting(
                    key=CHAT_PROMPT_PRESETS_SETTING_KEY,
                    value_json=value_json,
                    updated_by=updated_by,
                )
            )
        else:
            row.value_json = value_json
            row.updated_by = updated_by
        await self.db.commit()
        return PromptPresetListResponse(presets=validated)

    async def reset_presets(self) -> PromptPresetListResponse:
        """Reset stored presets to built-in defaults."""
        row = await self._load_row()
        if row is not None:
            await self.db.delete(row)
            await self.db.commit()
        return PromptPresetListResponse(presets=default_prompt_presets())
