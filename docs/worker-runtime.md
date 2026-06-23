# Worker Runtime

Workers execute processing tasks claimed from the backend. They can run in
different runtime profiles depending on host capabilities and workload.

## Capabilities

Workers advertise capabilities such as document, image, video, and training.
Task routing uses these capabilities to match work to workers.

Audio files are currently handled through the media/video capability path
because media processing shares the same runtime lane.

## Task Lifecycle

1. Worker authenticates with the backend using the worker token.
2. Worker polls for claimable tasks matching its capabilities.
3. Backend marks the task claimed, records `claimed_by`, and returns task id and
   task secret.
4. Worker performs task-scoped backend operations with `X-Task-Secret`.
5. Worker heartbeats while processing.
6. Worker completes or fails the task.

Task secrets are only valid for actively claimed tasks owned by the
authenticated worker.

## Backend Client

The worker's backend client talks to task-scoped routes for content-specific
operations. This includes:

- Downloading source files.
- Uploading extracted artifacts.
- Upserting vectors.
- Calling task-scoped embedding/token-count endpoints.
- Calling task-scoped VLM/document extraction LLM proxies.
- Loading allowed registry model artifacts.

Worker-wide config remains available for non-secret runtime configuration.

## Document Processing

Document processing generally follows:

1. Source content download.
2. Text/media extraction.
3. Chunk construction.
4. Optional classification.
5. Optional structured extraction.
6. Artifact upload.
7. Vector indexing.
8. Task completion.

Workers should preserve evidence metadata where possible: chunk indices, page
numbers, document references, image references, snippets, and matched queries.

## Runtime Profiles

Worker dependency profiles live under `worker/requirements/`.

Common profiles:

- CPU document/image runtime.
- CUDA runtime for Linux NVIDIA hosts.
- MPS runtime for macOS host execution.

The root README has the current command examples for building Docker images, and
`worker/README.md` has the manual worker development commands.

## Local Development

The Compose worker is disabled by default for local development. On macOS, run
the worker directly so Torch can use Apple MPS:

```bash
cd worker
cp ../VERSION VERSION
pip install -e '.[mps,test]'
API_URL=http://localhost:8000 WORKER_TOKEN=... CLASSIFICATION_DEVICE=mps \
  intextum-worker --capabilities document,video,image,training
```

Set:

- `WORKER_TOKEN`
- `API_URL`
- optional runtime/profile variables such as `CLASSIFICATION_DEVICE` and
  `ASR_MODEL`

## Auth Invariants

Workers should not receive provider secrets. Calls that need secrets are proxied
through the backend after task authorization.

Any worker code that touches file content or content-specific model operations
should carry task id and task secret through the call stack.
