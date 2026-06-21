# Worker Requirements

Requirement files are grouped by runtime concern:

- `base.txt`: small shared worker runtime dependencies.
- `document.txt`: Docling document/image conversion and OCR engines.
- `asr.txt`: Docling audio transcription extras.
- `content-enrichment.txt`: GLiNER2 classification and chat extraction dependencies.
- `cpu.txt`: feature-complete Linux CPU worker.
- `cpu-document.txt`: lighter Linux CPU worker for document/image processing only.
- `cuda.txt`: feature-complete Linux NVIDIA CUDA worker.
- `macos-mps.txt`: feature-complete macOS host worker for Apple MPS.
- `test.txt`: worker test dependencies only.

The default Docker CPU image installs `cpu.txt`. To build the lighter
document-only CPU image:

```bash
docker build -f worker/Dockerfile --build-arg WORKER_REQUIREMENTS=cpu-document.txt worker
```

Generated lock files are intentionally not checked in yet because these profiles
span macOS, Linux CPU, Linux CUDA, and architecture-specific Torch wheels. Use
`worker/scripts/compile-requirements.sh` on the target platform when you want a
local fully pinned file for one profile.
