"""Verify every policy-protected table has RLS enabled and forced.

This catches two classes of regression:

* A new table added to the schema but missing from ``020_policies.sql``.
* A future edit that drops ``ENABLE`` or ``FORCE ROW LEVEL SECURITY`` from an
  existing table.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


# Tables that are intentionally protected by RLS. Keep in sync with
# backend/sql/rls/020_policies.sql.
RLS_TABLES = sorted(
    [
        "workers",
        "indexed_content_items",
        "content_item_enrichment_states",
        "content_chunks",
        "content_audit_events",
        "content_item_file_details",
        "content_item_folder_details",
        "content_item_email_message_details",
        "content_item_attachment_details",
        "app_users",
        "user_identities",
        "local_credentials",
        "groups",
        "group_memberships",
        "group_external_aliases",
        "conversations",
        "data_sources",
        "permissions",
        "task_queue",
        "event_outbox",
        "content_enrichment_model_registry",
        "content_enrichment_fine_tune_jobs",
        "chat_runs",
        "research_reports",
        "app_settings",
        "document_classes",
        "extraction_schemas",
        "user_notification_preferences",
    ]
)

# Tables in the public schema that are deliberately *not* under RLS (e.g.
# Alembic metadata, framework-managed tables). Keep this list small and
# explicit — anything new should either be added to RLS_TABLES above or here.
EXEMPT_TABLES: set[str] = {
    "alembic_version",
}


@pytest.mark.parametrize("table", RLS_TABLES)
def test_table_has_rls_enabled_and_forced(app_conn, rls_database, table):
    row = app_conn.execute(
        """
        SELECT relrowsecurity, relforcerowsecurity
        FROM pg_class
        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
        WHERE pg_namespace.nspname = 'public' AND relname = %s
        """,
        (table,),
    ).fetchone()
    assert row is not None, f"{table} does not exist in the public schema"
    assert row == (True, True), (
        f"{table} must have RLS enabled and forced "
        f"(relrowsecurity={row[0]}, relforcerowsecurity={row[1]})"
    )


def test_no_public_table_is_silently_missing_rls(app_conn, rls_database):
    """Every public table must be either in RLS_TABLES or EXEMPT_TABLES.

    Catches the case where a new model is added but its table is never
    registered with the RLS policy SQL.
    """
    rows = app_conn.execute(
        """
        SELECT relname, relrowsecurity, relforcerowsecurity
        FROM pg_class
        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
        WHERE pg_namespace.nspname = 'public'
          AND relkind = 'r'
        ORDER BY relname
        """
    ).fetchall()

    known = set(RLS_TABLES) | EXEMPT_TABLES
    unknown = [name for (name, _, _) in rows if name not in known]
    assert unknown == [], (
        "New public tables are not registered with RLS. Add them to "
        f"RLS_TABLES (with policies in 020_policies.sql) or EXEMPT_TABLES: {unknown}"
    )

    missing_rls = [
        name
        for (name, force_enabled, force_forced) in rows
        if name in RLS_TABLES and not (force_enabled and force_forced)
    ]
    assert missing_rls == [], (
        f"Tables listed in RLS_TABLES but not actually enforced: {missing_rls}"
    )
