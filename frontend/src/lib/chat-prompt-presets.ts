import type { ChatPromptPreset } from "@/dataProvider";

export const PROMPT_PRESET_LOCALES = ["en", "de"] as const;

export type PromptPresetLocale = (typeof PROMPT_PRESET_LOCALES)[number];

export const PROMPT_PRESET_ICONS = [
  "bar-chart",
  "book-open",
  "file-search",
  "file-text",
  "list-checks",
  "search",
  "sparkles",
] as const;

export const localizedPresetText = (
  values: Record<string, string>,
  locale: string,
  fallback = "",
): string => {
  const normalizedLocale = locale.trim().toLowerCase();
  return (
    values[normalizedLocale]?.trim() ||
    values[normalizedLocale.split("-")[0]]?.trim() ||
    values.en?.trim() ||
    Object.values(values)
      .find((value) => value.trim())
      ?.trim() ||
    fallback
  );
};

export const normalizePromptPresetLocale = (locale: string): PromptPresetLocale => {
  const normalized = locale.trim().toLowerCase().split("-")[0];
  return normalized === "de" ? "de" : "en";
};

export const otherPromptPresetLocale = (locale: string): PromptPresetLocale =>
  normalizePromptPresetLocale(locale) === "de" ? "en" : "de";

export const availablePromptPresetLocales = (preset: Pick<ChatPromptPreset, "label">): string[] =>
  PROMPT_PRESET_LOCALES.filter((locale) => Boolean(preset.label[locale]?.trim()));

export const promptPresetLanguageBadge = (preset: Pick<ChatPromptPreset, "label">): string => {
  const locales = availablePromptPresetLocales(preset);
  return locales.length > 0 ? locales.map((locale) => locale.toUpperCase()).join(" + ") : "-";
};

export const preferredPromptPresetLocale = (
  preset: Pick<ChatPromptPreset, "label">,
  locale: string,
): PromptPresetLocale => {
  const normalized = normalizePromptPresetLocale(locale);
  if (preset.label[normalized]?.trim()) {
    return normalized;
  }
  const fallbackLocale = PROMPT_PRESET_LOCALES.find((candidate) => preset.label[candidate]?.trim());
  return fallbackLocale ?? normalized;
};

export const promptPresetRequirementMessageKey = (
  preset: ChatPromptPreset,
  selectedFileCount: number,
): "min" | "max" | null => {
  if (selectedFileCount < preset.context.min_files) {
    return "min";
  }
  if (
    typeof preset.context.max_files === "number" &&
    selectedFileCount > preset.context.max_files
  ) {
    return "max";
  }
  return null;
};

export const createPromptPresetId = (label: string): string => {
  const normalized = label
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const suffix = Math.random().toString(36).slice(2, 8);
  return `${normalized || "preset"}_${suffix}`;
};

export const nextPromptPresetSortOrder = (presets: ChatPromptPreset[]): number =>
  presets.reduce((max, preset) => Math.max(max, preset.sort_order), 0) + 10;
