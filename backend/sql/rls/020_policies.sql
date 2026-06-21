-- Row-level security policies for every app table.
--
-- All policies read the request context populated by backend/rls.py:
--   app.actor, app.user_sub, app.trustees, app.is_admin,
--   app.worker_id, app.task_id, app.content_item_id
--
-- Tables use FORCE ROW LEVEL SECURITY so the owning role (used only by
-- migrations) is the sole bypass path.

-- --- Enable + force RLS on every managed table -------------------------------

ALTER TABLE workers ENABLE ROW LEVEL SECURITY;
ALTER TABLE workers FORCE ROW LEVEL SECURITY;

ALTER TABLE indexed_content_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE indexed_content_items FORCE ROW LEVEL SECURITY;

ALTER TABLE content_item_enrichment_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_item_enrichment_states FORCE ROW LEVEL SECURITY;

ALTER TABLE content_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_chunks FORCE ROW LEVEL SECURITY;

ALTER TABLE content_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_audit_events FORCE ROW LEVEL SECURITY;

ALTER TABLE content_item_file_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_item_file_details FORCE ROW LEVEL SECURITY;

ALTER TABLE content_item_folder_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_item_folder_details FORCE ROW LEVEL SECURITY;

ALTER TABLE content_item_email_message_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_item_email_message_details FORCE ROW LEVEL SECURITY;

ALTER TABLE content_item_attachment_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_item_attachment_details FORCE ROW LEVEL SECURITY;

ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_users FORCE ROW LEVEL SECURITY;

ALTER TABLE user_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_identities FORCE ROW LEVEL SECURITY;

ALTER TABLE local_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE local_credentials FORCE ROW LEVEL SECURITY;

ALTER TABLE groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE groups FORCE ROW LEVEL SECURITY;

ALTER TABLE group_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE group_memberships FORCE ROW LEVEL SECURITY;

ALTER TABLE group_external_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE group_external_aliases FORCE ROW LEVEL SECURITY;

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;

ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_sources FORCE ROW LEVEL SECURITY;

ALTER TABLE permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE permissions FORCE ROW LEVEL SECURITY;

ALTER TABLE task_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_queue FORCE ROW LEVEL SECURITY;

ALTER TABLE event_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_outbox FORCE ROW LEVEL SECURITY;

ALTER TABLE content_enrichment_model_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_enrichment_model_registry FORCE ROW LEVEL SECURITY;

ALTER TABLE content_enrichment_fine_tune_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_enrichment_fine_tune_jobs FORCE ROW LEVEL SECURITY;

ALTER TABLE chat_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE research_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_reports FORCE ROW LEVEL SECURITY;

ALTER TABLE app_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings FORCE ROW LEVEL SECURITY;

ALTER TABLE document_classes ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_classes FORCE ROW LEVEL SECURITY;

ALTER TABLE extraction_schemas ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_schemas FORCE ROW LEVEL SECURITY;

ALTER TABLE user_notification_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_notification_preferences FORCE ROW LEVEL SECURITY;

-- --- workers -----------------------------------------------------------------

DROP POLICY IF EXISTS workers_rls ON workers;
CREATE POLICY workers_rls ON workers
    FOR ALL
    USING (
        app.is_admin()
        OR (
            app.current_actor() = 'worker_claim'
            AND (app.current_worker_id() = '' OR id = app.current_worker_id())
        )
    )
    WITH CHECK (
        app.is_admin()
        OR (
            app.current_actor() = 'worker_claim'
            AND id = app.current_worker_id()
        )
    );

-- --- indexed_content_items and child detail tables ---------------------------

DROP POLICY IF EXISTS indexed_content_items_rls ON indexed_content_items;
CREATE POLICY indexed_content_items_rls ON indexed_content_items
    FOR ALL
    USING (
        app.can_view_acl(allowed_viewers, denied_viewers)
        OR app.can_worker_task_access(content_item_id)
        OR app.current_actor() IN ('watcher', 'event_outbox', 'stale_cleanup')
    );

-- Content child tables: visible when either the parent indexed_content_items
-- row is accessible to the actor, OR the actor is the worker_task currently
-- processing the content (the indexed_content_items row may not exist yet).

DROP POLICY IF EXISTS content_item_enrichment_states_rls ON content_item_enrichment_states;
CREATE POLICY content_item_enrichment_states_rls ON content_item_enrichment_states
    FOR ALL
    USING (
        app.can_access_content_item(content_item_id)
        OR (
            app.current_actor() = 'worker_task'
            AND content_item_id = app.current_content_item_id()
        )
    );

DROP POLICY IF EXISTS content_chunks_rls ON content_chunks;
CREATE POLICY content_chunks_rls ON content_chunks
    FOR ALL
    USING (
        app.can_access_content_item(content_item_id)
        OR (
            app.current_actor() = 'worker_task'
            AND content_item_id = app.current_content_item_id()
        )
    );

DROP POLICY IF EXISTS content_item_file_details_rls ON content_item_file_details;
CREATE POLICY content_item_file_details_rls ON content_item_file_details
    FOR ALL
    USING (
        app.can_access_content_item(content_item_id)
        OR (
            app.current_actor() = 'worker_task'
            AND content_item_id = app.current_content_item_id()
        )
    );

DROP POLICY IF EXISTS content_item_folder_details_rls ON content_item_folder_details;
CREATE POLICY content_item_folder_details_rls ON content_item_folder_details
    FOR ALL
    USING (
        app.can_access_content_item(content_item_id)
        OR (
            app.current_actor() = 'worker_task'
            AND content_item_id = app.current_content_item_id()
        )
    );

DROP POLICY IF EXISTS content_item_email_message_details_rls ON content_item_email_message_details;
CREATE POLICY content_item_email_message_details_rls ON content_item_email_message_details
    FOR ALL
    USING (
        app.can_access_content_item(content_item_id)
        OR (
            app.current_actor() = 'worker_task'
            AND content_item_id = app.current_content_item_id()
        )
    );

DROP POLICY IF EXISTS content_item_attachment_details_rls ON content_item_attachment_details;
CREATE POLICY content_item_attachment_details_rls ON content_item_attachment_details
    FOR ALL
    USING (
        app.can_access_content_item(content_item_id)
        OR (
            app.current_actor() = 'worker_task'
            AND content_item_id = app.current_content_item_id()
        )
    );

DROP POLICY IF EXISTS content_audit_events_rls ON content_audit_events;
CREATE POLICY content_audit_events_rls ON content_audit_events
    FOR ALL
    USING (app.is_admin() OR app.can_access_content_item(content_item_id))
    WITH CHECK (
        app.is_admin()
        OR (
            app.current_actor() = 'worker_task'
            AND content_item_id = app.current_content_item_id()
        )
        OR app.current_actor() IN ('watcher', 'event_outbox', 'stale_cleanup')
        OR (
            app.current_actor() = 'user'
            AND (
                app.can_access_content_item(content_item_id)
                OR (
                    actor_sub = app.current_user_sub()
                    AND NOT app.content_item_exists_any(content_item_id)
                )
            )
        )
    );

-- --- users, identities, credentials, groups ----------------------------------

-- Split SELECT and write policies so the auth actor can look up users (during
-- session resolution / OAuth proxy sync) without being able to mutate rows
-- that don't belong to it.

DROP POLICY IF EXISTS app_users_rls ON app_users;
CREATE POLICY app_users_rls ON app_users
    FOR SELECT
    USING (
        app.is_admin()
        OR app.current_actor() = 'auth'
        OR sub = app.current_user_sub()
    );

DROP POLICY IF EXISTS app_users_admin_write_rls ON app_users;
CREATE POLICY app_users_admin_write_rls ON app_users
    FOR ALL
    USING (app.is_admin() OR app.current_actor() = 'auth')
    WITH CHECK (app.is_admin() OR app.current_actor() = 'auth');

DROP POLICY IF EXISTS user_identities_rls ON user_identities;
CREATE POLICY user_identities_rls ON user_identities
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() = 'auth'
        OR user_sub = app.current_user_sub()
    )
    WITH CHECK (app.is_admin() OR app.current_actor() = 'auth');

DROP POLICY IF EXISTS local_credentials_rls ON local_credentials;
CREATE POLICY local_credentials_rls ON local_credentials
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() = 'auth'
        OR user_sub = app.current_user_sub()
    )
    WITH CHECK (
        app.is_admin()
        OR app.current_actor() = 'auth'
        OR user_sub = app.current_user_sub()
    );

DROP POLICY IF EXISTS groups_rls ON groups;
CREATE POLICY groups_rls ON groups
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() IN (
            'auth', 'worker_claim', 'worker_task',
            'watcher', 'stale_cleanup', 'event_outbox', 'chat_runner'
        )
    )
    WITH CHECK (app.is_admin());

DROP POLICY IF EXISTS group_memberships_rls ON group_memberships;
CREATE POLICY group_memberships_rls ON group_memberships
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() = 'auth'
        OR user_sub = app.current_user_sub()
    )
    WITH CHECK (app.is_admin() OR app.current_actor() = 'auth');

DROP POLICY IF EXISTS group_external_aliases_rls ON group_external_aliases;
CREATE POLICY group_external_aliases_rls ON group_external_aliases
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() IN (
            'auth', 'worker_claim', 'worker_task',
            'watcher', 'stale_cleanup', 'event_outbox', 'chat_runner'
        )
    )
    WITH CHECK (app.is_admin() OR app.current_actor() = 'auth');

-- --- conversations / chat runs / research reports ----------------------------

DROP POLICY IF EXISTS conversations_rls ON conversations;
CREATE POLICY conversations_rls ON conversations
    FOR ALL
    USING (app.is_admin() OR user_sub = app.current_user_sub());

DROP POLICY IF EXISTS conversations_chat_runner_rls ON conversations;
CREATE POLICY conversations_chat_runner_rls ON conversations
    FOR ALL
    USING (
        app.current_actor() = 'chat_runner'
        AND EXISTS (
            SELECT 1 FROM chat_runs run
            WHERE run.conversation_id = conversations.id
              AND run.status = 'RUNNING'
        )
    )
    WITH CHECK (
        app.current_actor() = 'chat_runner'
        AND EXISTS (
            SELECT 1 FROM chat_runs run
            WHERE run.conversation_id = conversations.id
              AND run.status = 'RUNNING'
        )
    );

DROP POLICY IF EXISTS chat_runs_rls ON chat_runs;
CREATE POLICY chat_runs_rls ON chat_runs
    FOR ALL
    USING (
        app.is_admin()
        OR user_sub = app.current_user_sub()
        OR app.current_actor() = 'chat_runner'
    )
    WITH CHECK (
        app.is_admin()
        OR user_sub = app.current_user_sub()
        OR app.current_actor() = 'chat_runner'
    );

DROP POLICY IF EXISTS research_reports_rls ON research_reports;
CREATE POLICY research_reports_rls ON research_reports
    FOR ALL
    USING (
        app.is_admin()
        OR user_sub = app.current_user_sub()
        OR (
            app.current_actor() = 'chat_runner'
            AND EXISTS (
                SELECT 1 FROM chat_runs run
                WHERE run.research_report_id = research_reports.id
                  AND run.status = 'RUNNING'
            )
        )
    )
    WITH CHECK (
        app.is_admin()
        OR user_sub = app.current_user_sub()
        OR (
            app.current_actor() = 'chat_runner'
            AND EXISTS (
                SELECT 1 FROM chat_runs run
                WHERE run.research_report_id = research_reports.id
                  AND run.status = 'RUNNING'
            )
        )
    );

-- --- data sources / permissions ----------------------------------------------

DROP POLICY IF EXISTS data_sources_rls ON data_sources;
CREATE POLICY data_sources_rls ON data_sources
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() IN (
            'user', 'watcher', 'worker_claim', 'worker_task', 'event_outbox'
        )
    )
    WITH CHECK (app.is_admin());

DROP POLICY IF EXISTS permissions_rls ON permissions;
CREATE POLICY permissions_rls ON permissions
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() IN ('user', 'watcher', 'event_outbox')
    )
    WITH CHECK (app.is_admin());

-- --- task queue --------------------------------------------------------------

DROP POLICY IF EXISTS task_queue_rls ON task_queue;
CREATE POLICY task_queue_rls ON task_queue
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() IN ('watcher', 'stale_cleanup', 'event_outbox')
        OR (
            app.current_actor() = 'worker_claim'
            AND (
                status = 'PENDING'
                OR (status = 'CLAIMED' AND claimed_by = app.current_worker_id())
            )
        )
        OR (
            app.current_actor() = 'worker_task'
            AND id = app.current_task_id()
            AND content_item_id = app.current_content_item_id()
            AND (
                claimed_by = app.current_worker_id()
                OR (status = 'PENDING' AND claimed_by IS NULL)
            )
        )
    )
    WITH CHECK (
        app.is_admin()
        OR app.current_actor() IN ('watcher', 'stale_cleanup', 'event_outbox')
        OR (
            app.current_actor() = 'worker_claim'
            AND (
                status = 'PENDING'
                OR (status = 'CLAIMED' AND claimed_by = app.current_worker_id())
            )
        )
        OR (
            app.current_actor() = 'worker_task'
            AND id = app.current_task_id()
            AND content_item_id = app.current_content_item_id()
            AND (
                claimed_by = app.current_worker_id()
                OR (status = 'PENDING' AND claimed_by IS NULL)
            )
        )
    );

-- --- event outbox ------------------------------------------------------------

DROP POLICY IF EXISTS event_outbox_rls ON event_outbox;
CREATE POLICY event_outbox_rls ON event_outbox
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() = 'event_outbox'
        OR user_sub = app.current_user_sub()
    )
    WITH CHECK (
        app.is_admin()
        OR app.current_actor() IN ('watcher', 'event_outbox', 'stale_cleanup')
        OR (
            app.current_actor() = 'worker_task'
            AND aggregate_id = app.current_content_item_id()
        )
        OR (
            app.current_actor() = 'user'
            AND user_sub = app.current_user_sub()
        )
    );

-- --- enrichment registry / fine-tune jobs ------------------------------------

DROP POLICY IF EXISTS content_enrichment_model_registry_rls ON content_enrichment_model_registry;
CREATE POLICY content_enrichment_model_registry_rls ON content_enrichment_model_registry
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() = 'stale_cleanup'
        OR (
            app.current_actor() = 'worker_task'
            AND id = app.current_content_item_id()
        )
    )
    WITH CHECK (
        app.is_admin()
        OR app.current_actor() = 'stale_cleanup'
        OR (
            app.current_actor() = 'worker_task'
            AND id = app.current_content_item_id()
        )
    );

DROP POLICY IF EXISTS content_enrichment_fine_tune_jobs_rls ON content_enrichment_fine_tune_jobs;
CREATE POLICY content_enrichment_fine_tune_jobs_rls ON content_enrichment_fine_tune_jobs
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() = 'stale_cleanup'
        OR (
            app.current_actor() = 'worker_task'
            AND (
                queue_task_id = app.current_task_id()
                OR registry_model_id = app.current_content_item_id()
            )
        )
    )
    WITH CHECK (
        app.is_admin()
        OR app.current_actor() = 'stale_cleanup'
        OR (
            app.current_actor() = 'worker_task'
            AND (
                queue_task_id = app.current_task_id()
                OR registry_model_id = app.current_content_item_id()
            )
        )
    );

-- --- app settings / classes / schemas ----------------------------------------

DROP POLICY IF EXISTS app_settings_rls ON app_settings;
CREATE POLICY app_settings_rls ON app_settings
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() IN (
            'auth', 'worker_claim', 'worker_task',
            'watcher', 'stale_cleanup', 'event_outbox', 'chat_runner'
        )
    )
    WITH CHECK (app.is_admin() OR app.current_actor() = 'auth');

DROP POLICY IF EXISTS document_classes_rls ON document_classes;
CREATE POLICY document_classes_rls ON document_classes
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() IN (
            'auth', 'worker_claim', 'worker_task',
            'watcher', 'stale_cleanup', 'event_outbox', 'chat_runner'
        )
    )
    WITH CHECK (app.is_admin());

DROP POLICY IF EXISTS extraction_schemas_rls ON extraction_schemas;
CREATE POLICY extraction_schemas_rls ON extraction_schemas
    FOR ALL
    USING (
        app.is_admin()
        OR app.current_actor() IN (
            'auth', 'worker_claim', 'worker_task',
            'watcher', 'stale_cleanup', 'event_outbox', 'chat_runner'
        )
    )
    WITH CHECK (app.is_admin());

-- --- user notification preferences -------------------------------------------

DROP POLICY IF EXISTS user_notification_preferences_rls ON user_notification_preferences;
CREATE POLICY user_notification_preferences_rls ON user_notification_preferences
    FOR ALL
    USING (app.is_admin() OR user_sub = app.current_user_sub())
    WITH CHECK (app.is_admin() OR user_sub = app.current_user_sub());
