#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${WORKER_DIR}"

if [[ ! -x ".venv-mps/bin/python" ]]; then
  echo "Missing worker/.venv-mps. Run worker/scripts/setup-macos-mps.sh first." >&2
  exit 1
fi

. .venv-mps/bin/activate

export CLASSIFICATION_DEVICE="${CLASSIFICATION_DEVICE:-mps}"
export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"
export DOCLING_OCR_ENGINE="${DOCLING_OCR_ENGINE:-ocrmac}"
export ASR_MODEL="${ASR_MODEL:-whisper_large_v3}"
export WORK_DIR="${WORK_DIR:-/tmp/intextum-worker}"

exec intextum-worker "$@"
