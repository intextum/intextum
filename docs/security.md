# Security Test Map

This note points future refactors to the tests that pin the current security
boundaries. It intentionally tracks test ownership rather than deployment
hardening.

## Worker Task Boundary

- `api/tests/test_worker_task_security.py`
- `api/tests/test_worker_embedding_proxy.py`
- `api/tests/test_worker_vlm_proxy.py`
- `api/tests/test_worker_vector_upsert.py`
- `api/tests/integration/test_rls_task_lifecycle_boundary.py`
- `api/tests/integration/test_rls_worker_isolation.py`
- `api/tests/integration/test_rls_task_workflows.py`
- `api/tests/integration/test_rls_policy_access.py`

These cover worker-token authentication, task-secret scope, stale or terminal
task rejection, vector upsert lifecycle boundaries, worker isolation, and the
special completed-task audit path.

## RLS And Content Visibility

- `api/tests/integration/test_rls_force_enabled.py`
- `api/tests/integration/test_rls_role_privileges.py`
- `api/tests/integration/test_rls_content_lifecycle.py`
- `api/tests/integration/test_rls_user_ownership.py`
- `api/tests/integration/test_rls_chat_runner.py`
- `api/tests/test_vector_service.py`
- `api/tests/test_acl_service.py`

These cover forced RLS, runtime role privilege limits, content ACL visibility,
denied-content vector retrieval, semantic search visibility, chat-runner owner
scope, and the intentional choice to leave ACL filtering to Postgres RLS.

## Admin Boundaries

- `api/tests/integration/test_rls_admin_denials.py`
- `api/tests/integration/test_rls_admin_services.py`
- `api/tests/test_content_enrichment_training_router.py`
- `api/tests/test_chat_prompt_presets_router.py`

These cover service-level admin denials plus router-level admin-only endpoint
authorization.
