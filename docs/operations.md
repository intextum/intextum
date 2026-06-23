# Operations

This page collects common development and maintenance commands.

## Local Stack

Create local config:

```bash
cp config.example.yaml config.yaml
```

Start the development stack:

```bash
docker compose up --build
```

The Compose stack is for development. For macOS worker work, prefer the host
worker scripts described in [Worker Runtime](worker-runtime.md).

## Database Migrations

Migration policy while the stack is still local-only:

- The squashed `001_initial.py` baseline may be reset only by explicit choice.
- Once the baseline is treated as fixed, schema changes should be forward-only
  Alembic revisions.
- If a model change intentionally lands before the freeze, update the baseline
  schema snapshot test in the same change.
- If a model change happens after the freeze, leave the baseline snapshot alone
  and add a migration instead.

Check the current Alembic revision in the backend container:

```bash
docker compose exec api python -m alembic current
```

Apply migrations:

```bash
docker compose exec api python -m alembic upgrade head
```

When a development migration baseline is intentionally reset, recreate the local
Postgres volume:

```bash
docker compose down -v
docker compose up --build
```

The current baseline enables Postgres row-level security and creates the
non-owner runtime role from `postgres_app_user` / `postgres_app_password`.
Changing those values requires recreating the local Postgres volume.
Alembic and LangGraph checkpointer schema setup use owner credentials; normal
backend runtime connections use the non-owner role.

This discards local database data.

## Backend Tests

Focused backend checks usually use `.venv-backend-checks`:

```bash
.venv-backend-checks/bin/pytest api/tests/test_auth.py
```

Install or refresh backend test dependencies:

```bash
.venv-backend-checks/bin/pip install -r api/requirements-test.txt
```

Ruff:

```bash
.venv-backend-checks/bin/ruff check api worker
```

Syntax/import smoke:

```bash
python3 -m compileall api/models api/services api/routers api/tests worker/models.py worker/services worker/tests
```

RLS integration tests start a test-only Postgres/pgvector container through
pytest-docker and must disable the unit-test DB engine mock:

```bash
INTEXTUM_TEST_REAL_DB=1 INTEXTUM_RUN_INTEGRATION=1 \
.venv-backend-checks/bin/pytest api/tests/integration -m integration
```

Set `POSTGRES_HOST` and `POSTGRES_PORT` when you intentionally want to reuse an
already running external database instead.

## Worker Tests

Use the Python 3.12 root virtualenv for worker tests:

```bash
.venv/bin/pytest worker/tests/test_content_enrichment.py worker/tests/test_api_client.py
```

The older `worker/.venv` may be Python 3.11 and can fail to parse current
Python 3.12 syntax.

## Frontend Checks

Run lint:

```bash
npm run lint
```

Run the frontend test suite from `web/`:

```bash
npm run test
```

Focused content-enrichment/admin tests:

```bash
npm run test -- --run src/lib/content-enrichment-admin.test.ts
```

## Content Enrichment Smoke

For extraction/classification demo readiness:

1. Confirm Alembic migrations are applied.
2. Define document classes and extraction schemas in admin settings.
3. Prefer shared scenes for multi-field examples.
4. Process one representative document.
5. Check worker logs for extraction failures, empty assistant messages,
   `finish_reason=length`, or JSON parse issues.
6. Review extracted fields, evidence, and stale status in the UI.

If extraction is unstable, first tune config:

- Increase `document_extraction_llm_max_output_tokens`.
- Switch `document_extraction_chunk_strategy` to `selected` for large files.
- Try a model with better JSON response behavior.

## Commit Hygiene

Formatting and linting run automatically on staged files via
[pre-commit](https://pre-commit.com). Install the git hook once per clone:

```bash
pip install pre-commit
pre-commit install
(cd web && npm ci)   # eslint/prettier hooks reuse web/node_modules
```

The hooks run ruff (check + format) on `api/` and `worker/`, and eslint +
prettier on `web/`. Run them across the whole repo with
`pre-commit run --all-files`. The same hooks gate CI (`.github/workflows/lint.yml`),
which is the enforcement point — the local hook can be bypassed with
`git commit --no-verify`.

Before committing:

```bash
git status --short
git diff --check
```

Run the smallest useful test set for the files changed, then broaden if shared
auth, catalog, task queue, or worker runtime behavior was touched.
