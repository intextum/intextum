#!/bin/sh
set -eu

escape_js() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

brand_title="${APP_BRAND_TITLE:-${VITE_APP_BRAND_TITLE:-Intextum}}"
# Subtitle intentionally has no default: when unset the app falls back to the
# version (see web/src/config/branding.ts).
brand_subtitle="${APP_BRAND_SUBTITLE:-${VITE_APP_BRAND_SUBTITLE:-}}"
# Canonical version comes from the mounted /VERSION file; APP_VERSION overrides.
version_file="$( [ -f /VERSION ] && tr -d '[:space:]' < /VERSION || true )"
app_version="${APP_VERSION:-${VITE_APP_VERSION:-$version_file}}"

cat > /usr/share/nginx/html/runtime-config.js <<EOF
window.__APP_CONFIG__ = {
  brandTitle: "$(escape_js "$brand_title")",
  brandSubtitle: "$(escape_js "$brand_subtitle")",
  version: "$(escape_js "$app_version")"
};
EOF
