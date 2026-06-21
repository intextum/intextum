#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROFILE="${1:-cpu.txt}"
OUTPUT="${2:-${WORKER_DIR}/requirements/locks/${PROFILE%.txt}.lock.txt}"

cd "${WORKER_DIR}"

python -m pip install --upgrade pip-tools
mkdir -p "$(dirname "${OUTPUT}")"
python -m piptools compile \
  --resolver=backtracking \
  --strip-extras \
  --output-file "${OUTPUT}" \
  "requirements/${PROFILE}"

echo "Wrote ${OUTPUT}"
