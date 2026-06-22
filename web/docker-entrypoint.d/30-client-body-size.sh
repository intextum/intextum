#!/bin/sh
set -eu

CONFIG_FILE="${CONFIG_FILE:-/config/config.yaml}"
CLIENT_BODY_SIZE_CONF="${NGINX_CLIENT_BODY_SIZE_CONF:-/etc/nginx/conf.d/client-body-size.conf}"
UPLOAD_OVERHEAD_BYTES="${NGINX_UPLOAD_OVERHEAD_BYTES:-1048576}"

yaml_value() {
  key="$1"
  [ -f "$CONFIG_FILE" ] || return 0
  awk -v key="$key" '
    /^[[:space:]]*#/ { next }
    $0 ~ "^[[:space:]]*" key "[[:space:]]*:" {
      sub("^[[:space:]]*" key "[[:space:]]*:[[:space:]]*", "")
      sub("[[:space:]]+#.*$", "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$CONFIG_FILE"
}

numeric_value() {
  value="$1"
  fallback="$2"
  case "$value" in
    ''|*[!0-9]*) printf '%s\n' "$fallback" ;;
    *) printf '%s\n' "$value" ;;
  esac
}

UPLOAD_OVERHEAD_BYTES="$(numeric_value "${UPLOAD_OVERHEAD_BYTES:-}" 1048576)"

configured_bytes() {
  yaml_key="$1"
  env_key="$2"
  fallback="$3"

  from_yaml="$(yaml_value "$yaml_key" || true)"
  if [ -n "$from_yaml" ]; then
    numeric_value "$from_yaml" "$fallback"
    return
  fi

  eval "from_env=\${$env_key:-}"
  numeric_value "$from_env" "$fallback"
}

if [ -n "${NGINX_CLIENT_MAX_BODY_SIZE:-}" ]; then
  body_size="$NGINX_CLIENT_MAX_BODY_SIZE"
else
  max_file="$(configured_bytes max_upload_file_size_bytes MAX_UPLOAD_FILE_SIZE_BYTES 52428800)"
  max_batch="$(configured_bytes max_upload_batch_size_bytes MAX_UPLOAD_BATCH_SIZE_BYTES 209715200)"
  max_model_artifact="$(configured_bytes max_model_artifact_upload_size_bytes MAX_MODEL_ARTIFACT_UPLOAD_SIZE_BYTES 536870912)"

  body_size="$max_file"
  [ "$max_batch" -gt "$body_size" ] && body_size="$max_batch"
  [ "$max_model_artifact" -gt "$body_size" ] && body_size="$max_model_artifact"
  body_size=$((body_size + UPLOAD_OVERHEAD_BYTES))
fi

cat > "$CLIENT_BODY_SIZE_CONF" <<EOF
client_max_body_size $body_size;
EOF
