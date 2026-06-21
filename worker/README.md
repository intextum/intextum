# intextum-worker

The Intextum processing worker: an HTTP-polling worker that pulls tasks from an
Intextum API instance and runs the Docling / FFmpeg document, image and audio
pipeline (OCR, ASR, chunking, classification, content enrichment, embeddings).

The worker is **always-remote**: it downloads source files from and uploads
results to the API over HTTP, so it does not need a shared volume and can run
anywhere — including on a host with a GPU while the rest of the stack runs in
Docker.

## Install

Pick the bundle that matches your accelerator. The macOS (Apple MPS) wheels are
on PyPI, so it installs with no extra flags:

```bash
pip install 'intextum-worker[mps]'
```

Linux CPU and NVIDIA CUDA pull their Torch build from the PyTorch index, so add
the matching `--extra-index-url`:

```bash
# Linux, CPU only
pip install 'intextum-worker[cpu]'  --extra-index-url https://download.pytorch.org/whl/cpu

# Linux, NVIDIA CUDA 12.6
pip install 'intextum-worker[cuda]' --extra-index-url https://download.pytorch.org/whl/cu126
```

Available extras: `mps`, `cpu`, `cuda`, `cpu-document` (document/image only), plus
the granular `document`, `asr`, `enrichment` stacks.

## Run

```bash
export API_URL="https://your-intextum-host"   # the API to poll
export WORKER_TOKEN="<token from the Add Worker dialog>"
intextum-worker --capabilities document,video,image
```

`intextum-worker --help` lists all flags. Every flag also has an environment
variable (`API_URL`, `WORKER_TOKEN`, `WORK_DIR`, `CAPABILITIES`, `POLL_INTERVAL`,
`CLASSIFICATION_DEVICE`, `DOCLING_OCR_ENGINE`, …); CLI flags take precedence.

## Development

This package uses a `src/` layout. The repo-root `VERSION` file is the single
source of truth for the version; it is staged into `worker/VERSION` at build time
(`worker/VERSION` is gitignored).

```bash
cp ../VERSION VERSION           # stage the version for an editable install
pip install -e '.[mps,test]'    # or [cpu,test] / [cuda,test]
pytest
```

On macOS, `scripts/setup-macos-mps.sh` does the venv + editable install for you,
and `scripts/run-macos-mps.sh` launches the worker with MPS defaults.
