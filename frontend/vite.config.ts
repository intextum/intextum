import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteStaticCopy } from "vite-plugin-static-copy";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "path";

const require = createRequire(import.meta.url);
const pdfjsDistPath = path.dirname(require.resolve("pdfjs-dist/package.json"));

// Single source of truth: the repo-root VERSION file. In the Docker build the
// root file is outside the build context, so fall back to package.json (and the
// runtime APP_VERSION env still overrides at container start).
const resolveAppVersion = (): string => {
  for (const candidate of [
    path.resolve(__dirname, "../VERSION"),
    path.resolve(__dirname, "VERSION"),
  ]) {
    try {
      const value = readFileSync(candidate, "utf-8").trim();
      if (value) return value;
    } catch {
      // file not present in this context; try the next candidate
    }
  }
  return process.env.npm_package_version ?? "0.0.0";
};

const appVersion = resolveAppVersion();

const allowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? process.env.APP_DOMAIN ?? "")
  .split(",")
  .map((host) => host.trim())
  .filter(Boolean);

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  plugins: [
    react(),
    tailwindcss(),
    viteStaticCopy({
      targets: [
        { src: path.join(pdfjsDistPath, "cmaps"), dest: "pdfjs" },
        { src: path.join(pdfjsDistPath, "standard_fonts"), dest: "pdfjs" },
        { src: path.join(pdfjsDistPath, "wasm"), dest: "pdfjs" },
      ],
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      xlsx: "xlsx/xlsx.mjs",
    },
  },
  server: {
    host: true,
    allowedHosts,
    watch: {
      usePolling: true,
    },
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
