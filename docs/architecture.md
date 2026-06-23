# Architecture

intextum is a local-first knowledge platform for unstructured files. It stores
files, extracts text and media-derived content, indexes chunks for semantic
search, enriches documents with classification and structured data, and exposes
chat/research workflows over the indexed content.

## Components

### Frontend

The frontend lives in `web/` and is a React/Vite application. It provides:

- Content browsing, review, and document-data inspection.
- Chat and research workflows.
- Admin settings for AI/runtime configuration.
- Content enrichment catalog editing for document classes and extraction
  schemas.

### Backend

The backend lives in `api/` and is a FastAPI application. It owns:

- User authentication and sessions.
- ACL checks and content access control.
- Content item metadata, extracted state, and processing lifecycle.
- Task queue coordination and worker authorization.
- AI runtime settings and content enrichment catalog persistence.
- Chat, research, search, and worker proxy endpoints.

The backend is the trust boundary for user data and provider secrets. Workers
receive task-specific access and call backend proxies for privileged operations.

### Worker

The worker lives in `worker/` and performs asynchronous processing:

- Document parsing and chunk generation.
- OCR/image/video/audio processing depending on runtime profile.
- Classification and structured extraction.
- Vector indexing and backend upload/upsert operations.
- Optional training/artifact workflows for content enrichment models.

Workers authenticate with a worker token and then use task secrets for
task-scoped operations.

### Storage

The development stack uses PostgreSQL with pgvector plus filesystem-backed data
directories. Important storage areas include:

- PostgreSQL tables for users, content items, ACLs, chunks, task queue rows,
  catalog entries, settings, and enrichment state.
- `data/` for local content volume data.
- `extracted/` for extracted artifacts and worker outputs.
- `model-artifacts/` for content-enrichment adapter artifacts.

## Main Data Flows

### Content Ingestion

1. A user or connector creates/updates a content item.
2. Backend records metadata, ACLs, and processing state.
3. Backend enqueues processing tasks.
4. A worker claims a task and receives a task id plus task secret.
5. Worker downloads task-authorized content from the backend.
6. Worker extracts text/media data, uploads artifacts, and indexes chunks.
7. Backend records completion and exposes searchable/reviewable state.

### Search And Chat

1. User submits a query or chat message.
2. Backend checks user identity and ACL scope.
3. Backend retrieves matching chunks/content metadata.
4. Chat graph injects system, file, and report context into a single leading
   system message before calling the configured chat model.
5. Backend streams responses and persists visible conversation state.

### Deep Research

Deep research is an asynchronous report-generation mode built on a separate
LangGraph workflow. It collects structured facts, plans report sections,
retrieves section-specific evidence, drafts cited sections, verifies citation
usage, stores a research report, and appends the completed report to the
conversation. See [Chat And Deep Research](research.md).

### Content Enrichment

1. Admin defines document classes and optional extraction schemas.
2. Backend persists catalog entries and exposes runtime labels/schemas.
3. Worker classifies documents when enabled.
4. Worker picks the matching extraction schema and extracts structured fields.
5. Backend validates and stores enrichment output with schema/class metadata.
6. Review UI shows extracted values, evidence, review state, and stale status.

## Versioning

Document classes and extraction schemas have separate lifecycle versions:

- Class version changes when class metadata changes.
- Schema version changes when extraction schema content changes, including
  fields and shared scenes.

The worker-facing schema version is stored with extraction results so existing
content can be detected as stale after schema changes.

## Development Stack

`docker-compose.yaml` is intended for development. Do not treat it as the source
of production traffic/security guarantees. The application-level security model
is still meaningful in development: auth, ACLs, task-scoped worker access, and
backend-held model credentials are enforced by the backend.
