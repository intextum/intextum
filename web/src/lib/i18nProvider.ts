import { en } from "../i18n/en";
import { de } from "../i18n/de";

export type TranslationMessages = Record<string, unknown>;

export const messages: Record<string, () => TranslationMessages> = {
  en: () => en,
  de: () => de,
};

export const availableLocales = [
  { locale: "en", name: "English" },
  { locale: "de", name: "Deutsch" },
];
