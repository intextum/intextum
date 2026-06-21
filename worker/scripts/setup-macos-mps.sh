#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${WORKER_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

cd "${WORKER_DIR}"

# Stage the shared root VERSION so the editable install can resolve its version.
cp "${REPO_ROOT}/VERSION" VERSION

"${PYTHON_BIN}" -m venv .venv-mps
. .venv-mps/bin/activate

python -m pip install --upgrade pip
# macOS Torch wheels are on PyPI, so the MPS extra installs with no extra index.
python -m pip install -e '.[mps]'

echo "macOS MPS worker environment ready at ${WORKER_DIR}/.venv-mps"
echo "Run it with: worker/scripts/run-macos-mps.sh"
