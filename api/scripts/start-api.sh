#!/bin/sh
set -eu

max_attempts="${MIGRATION_MAX_ATTEMPTS:-30}"
retry_seconds="${MIGRATION_RETRY_SECONDS:-2}"
attempt=1

while [ "$attempt" -le "$max_attempts" ]; do
    if alembic upgrade head; then
        break
    fi

    if [ "$attempt" -eq "$max_attempts" ]; then
        echo "Alembic migration failed after ${max_attempts} attempts." >&2
        exit 1
    fi

    echo "Alembic migration failed (attempt ${attempt}/${max_attempts}); retrying in ${retry_seconds}s..." >&2
    attempt=$((attempt + 1))
    sleep "$retry_seconds"
done

exec "$@"
