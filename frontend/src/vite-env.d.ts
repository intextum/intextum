/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_BRAND_TITLE?: string;
  readonly VITE_APP_BRAND_SUBTITLE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface AppRuntimeConfig {
  brandTitle?: string;
  brandSubtitle?: string;
  version?: string;
}

interface Window {
  __APP_CONFIG__?: AppRuntimeConfig;
}

// Injected at build time by Vite `define` (see vite.config.ts).
declare const __APP_VERSION__: string;
