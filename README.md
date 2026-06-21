# intextum

intextum is a local-first knowledge platform for unstructured files. It indexes documents and media, enables semantic search, and provides chat over your own data.

## What it does

- Ingests files from connected data sources
- Extracts and enriches text/media content in background workers
- Enables semantic search across indexed content
- Provides chat with answers grounded in stored documents
- Supports group-based access control

## Tech stack

- Frontend: React + Vite
- Backend API: FastAPI
- Worker: Python processing pipeline
- Storage: PostgreSQL + pgvector
- Auth: local app login with Valkey-backed sessions
- Runtime: Docker Compose

## Quick start (local)

1. Install Docker and Docker Compose.
2. Create a local `.env` file:
   ```bash
   cp .env.example .env
   ```
   `WORKER_TOKEN` can stay empty until you run an external worker.
3. Create `config.yaml` from the template and adjust values if needed:
   ```bash
   cp config.example.yaml config.yaml
   ```
   Set `auth_bootstrap_admin_password` to a strong value, for example from
   `openssl rand -base64 32`. Configure chat, embedding, and extraction models
   in this file.
4. Start the stack:
   ```bash
   docker compose up --build
   ```
5. Open the app at `http://<APP_DOMAIN>`.

If you pull an Alembic history squash that resets the migration baseline, recreate
your local Postgres volume before starting again:

```bash
docker compose down -v
docker compose up --build
```

This discards old local database data. In-place upgrades from the pre-squash
development migrations are not supported.

The current baseline also enables Postgres row-level security and creates the
non-owner runtime role from `postgres_app_user` / `postgres_app_password`.
Changing those credentials requires recreating the local Postgres volume.
Alembic and LangGraph checkpointer schema setup use owner credentials; normal
backend runtime connections use the non-owner role.

## Repository layout

- `frontend/` user interface
- `backend/` API, indexing, search, auth integration
- `worker/` async processing workers
- `data/` sample/attached data volumes
- `config.example.yaml` local configuration template

## Worker runtimes

The Docker Compose worker is disabled for local development by default. On macOS,
run the worker directly on the host so Torch can use Apple MPS:

```bash
worker/scripts/setup-macos-mps.sh
WORKER_TOKEN=... BACKEND_URL=http://localhost:8000 worker/scripts/run-macos-mps.sh
```

The host helper defaults to `CLASSIFICATION_DEVICE=mps`,
`PYTORCH_ENABLE_MPS_FALLBACK=1`, `DOCLING_OCR_ENGINE=ocrmac`,
`ASR_MODEL=whisper_large_v3`, and `WORK_DIR=/tmp/intextum-worker`.
Set `ASR_MODEL=whisper_medium` or `ASR_MODEL=whisper_turbo` when you prefer
speed over transcript quality.

Docker worker images are split by Linux runtime:

```bash
docker build -f worker/Dockerfile worker
docker build -f worker/Dockerfile.cuda worker
```

`worker/Dockerfile` is the CPU image and verifies that no `nvidia-*` packages are
installed. `worker/Dockerfile.cuda` targets Linux NVIDIA hosts with the NVIDIA
Container Toolkit; it is not intended for macOS Docker.

Worker requirements are grouped by runtime profile under `worker/requirements/`.
The default CPU/CUDA/MPS profiles are feature-complete. For a lighter
document/image-only CPU image:

```bash
docker build -f worker/Dockerfile --build-arg WORKER_REQUIREMENTS=cpu-document.txt worker
```

When running the worker directly on macOS, use the MPS helper so Docling, ASR,
and enrichment dependencies are installed into `worker/.venv-mps`:

```bash
worker/scripts/setup-macos-mps.sh
worker/scripts/run-macos-mps.sh --backend-url=http://127.0.0.1.nip.io/ --capabilities document,video,image,training
```

MP3/WAV/M4A tasks are claimed through the `video` capability because the worker
uses that capability for media processing.
