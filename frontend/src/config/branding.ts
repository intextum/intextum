const DEFAULT_BRAND_TITLE = "Intextum";

const normalizeBrandValue = (value?: string): string | undefined => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
};

const runtimeConfig = window.__APP_CONFIG__ ?? {};

// Shared application version. Resolution order: runtime config (set by the
// container entrypoint from APP_VERSION) → value baked in at build time from the
// repo-root VERSION file.
export const APP_VERSION = normalizeBrandValue(runtimeConfig.version) ?? __APP_VERSION__;

export const BRAND_TITLE =
  normalizeBrandValue(runtimeConfig.brandTitle) ??
  normalizeBrandValue(import.meta.env.VITE_APP_BRAND_TITLE) ??
  DEFAULT_BRAND_TITLE;

// When no explicit subtitle is configured, show the current version.
export const BRAND_SUBTITLE =
  normalizeBrandValue(runtimeConfig.brandSubtitle) ??
  normalizeBrandValue(import.meta.env.VITE_APP_BRAND_SUBTITLE) ??
  `v${APP_VERSION}`;
