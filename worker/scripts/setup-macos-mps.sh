#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
WORKER_REQUIREMENTS="${WORKER_REQUIREMENTS:-macos-mps.txt}"

cd "${WORKER_DIR}"

"${PYTHON_BIN}" -m venv .venv-mps
. .venv-mps/bin/activate

python -m pip install --upgrade pip
python -m pip install -r "requirements/${WORKER_REQUIREMENTS}"

echo "macOS MPS worker environment ready at ${WORKER_DIR}/.venv-mps"
