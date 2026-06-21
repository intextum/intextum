-- App schema and STABLE helper functions used by the RLS policies.
-- These read transaction-local GUCs that backend/rls.py populates on every
-- session via set_config('app.*', ..., true).

CREATE SCHEMA IF NOT EXISTS app;

CREATE OR REPLACE FUNCTION app.current_actor()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(NULLIF(current_setting('app.actor', true), ''), 'anonymous')
$$;

CREATE OR REPLACE FUNCTION app.current_user_sub()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(NULLIF(current_setting('app.user_sub', true), ''), '')
$$;

CREATE OR REPLACE FUNCTION app.current_worker_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(NULLIF(current_setting('app.worker_id', true), ''), '')
$$;

CREATE OR REPLACE FUNCTION app.current_task_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(NULLIF(current_setting('app.task_id', true), ''), '')
$$;

CREATE OR REPLACE FUNCTION app.current_content_item_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(NULLIF(current_setting('app.content_item_id', true), ''), '')
$$;

CREATE OR REPLACE FUNCTION app.current_trustees()
RETURNS text[]
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(array_agg(value), ARRAY[]::text[])
    FROM jsonb_array_elements_text(
        COALESCE(
            NULLIF(current_setting('app.trustees', true), '')::jsonb,
            '[]'::jsonb
        )
    ) AS value
$$;

CREATE OR REPLACE FUNCTION app.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(NULLIF(current_setting('app.is_admin', true), ''), 'false') = 'true'
$$;

CREATE OR REPLACE FUNCTION app.is_actor(VARIADIC actors text[])
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT app.current_actor() = ANY(actors)
$$;

CREATE OR REPLACE FUNCTION app.can_view_acl(allowed text[], denied text[])
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT
        app.is_admin()
        OR (
            COALESCE(allowed, ARRAY[]::text[]) && app.current_trustees()
            AND NOT (COALESCE(denied, ARRAY[]::text[]) && app.current_trustees())
        )
$$;

CREATE OR REPLACE FUNCTION app.can_worker_task_access(task_content_item_id text)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT
        app.current_actor() = 'worker_task'
        AND task_content_item_id = app.current_content_item_id()
        AND EXISTS (
            SELECT 1
            FROM task_queue task
            WHERE task.id = app.current_task_id()
              AND task.content_item_id = task_content_item_id
              AND task.claimed_by = app.current_worker_id()
              AND task.status = 'CLAIMED'
              AND task.task_secret IS NOT NULL
        )
$$;

CREATE OR REPLACE FUNCTION app.can_access_content_item(content_id text)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM indexed_content_items item
        WHERE item.content_item_id = content_id
          AND (
              app.can_view_acl(item.allowed_viewers, item.denied_viewers)
              OR app.can_worker_task_access(item.content_item_id)
              OR app.current_actor() IN ('watcher', 'event_outbox', 'stale_cleanup')
          )
    )
$$;

-- Used by content_audit_events: a user is allowed to write a "fallback" audit
-- row tagged with their own actor_sub *only* when no indexed_content_items row
-- exists for the referenced content_id (i.e. the audit predates the indexing).
-- SECURITY DEFINER so the bypass-existence check itself is not subject to
-- indexed_content_items RLS.
CREATE OR REPLACE FUNCTION app.content_item_exists_any(content_id text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM indexed_content_items item
        WHERE item.content_item_id = content_id
    )
$$;
