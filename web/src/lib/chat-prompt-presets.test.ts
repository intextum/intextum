import assert from "node:assert/strict";
import test from "node:test";

import {
  createPromptPresetId,
  preferredPromptPresetLocale,
  localizedPresetText,
  nextPromptPresetSortOrder,
  promptPresetLanguageBadge,
  promptPresetRequirementMessageKey,
} from "./chat-prompt-presets.ts";
import type { ChatPromptPreset } from "../dataProvider.ts";

const preset: ChatPromptPreset = {
  id: "demo",
  enabled: true,
  sort_order: 10,
  mode: "research",
  label: { en: "English", de: "Deutsch" },
  description: { en: "Description", de: "Beschreibung" },
  prompt: { en: "Prompt", de: "Prompt DE" },
  icon: "book-open",
  context: { min_files: 1, max_files: 2 },
  action: "fill",
};

test("localizedPresetText falls back from region to base locale and English", () => {
  assert.equal(localizedPresetText(preset.label, "de-DE"), "Deutsch");
  assert.equal(localizedPresetText({ en: "English" }, "fr"), "English");
  assert.equal(localizedPresetText({ de: "Deutsch" }, "en"), "Deutsch");
  assert.equal(localizedPresetText({}, "fr", "Fallback"), "Fallback");
});

test("prompt preset language badge lists available locales", () => {
  assert.equal(promptPresetLanguageBadge(preset), "EN + DE");
  assert.equal(promptPresetLanguageBadge({ label: { de: "Deutsch" } }), "DE");
});

test("preferredPromptPresetLocale uses requested locale then available fallback", () => {
  assert.equal(preferredPromptPresetLocale(preset, "de-DE"), "de");
  assert.equal(preferredPromptPresetLocale({ label: { de: "Deutsch" } }, "en"), "de");
  assert.equal(preferredPromptPresetLocale({ label: {} }, "de"), "de");
});

test("promptPresetRequirementMessageKey validates min and max selected files", () => {
  assert.equal(promptPresetRequirementMessageKey(preset, 0), "min");
  assert.equal(promptPresetRequirementMessageKey(preset, 1), null);
  assert.equal(promptPresetRequirementMessageKey(preset, 2), null);
  assert.equal(promptPresetRequirementMessageKey(preset, 3), "max");
});

test("nextPromptPresetSortOrder appends after the largest existing order", () => {
  assert.equal(nextPromptPresetSortOrder([preset, { ...preset, id: "b", sort_order: 30 }]), 40);
});

test("createPromptPresetId normalizes labels", () => {
  assert.match(createPromptPresetId("Ämter & Aufgaben"), /^amter_aufgaben_[a-z0-9]+$/);
});
