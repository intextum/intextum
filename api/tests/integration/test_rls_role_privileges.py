"""Verify the runtime app role cannot bypass RLS through privilege escalation.

The whole RLS design rests on the assumption that ``intextum_app`` (the runtime
role) is not a superuser, does not own the protected tables, and cannot
disable policies or escalate to the owner. If any of these become false,
RLS becomes advisory.
"""

from __future__ import annotations

import psycopg
import pytest


pytestmark = pytest.mark.integration


def _expect_denied(app_conn, statement: str, *, params: tuple = ()) -> None:
    """Assert that ``statement`` raises a privilege-related error."""
    with pytest.raises(
        (
            psycopg.errors.InsufficientPrivilege,
            psycopg.errors.SyntaxError,
            psycopg.errors.FeatureNotSupported,
            psycopg.errors.UndefinedTable,
        )
    ):
        with app_conn.transaction():
            app_conn.execute(statement, params)


def test_app_role_is_not_a_superuser(app_conn, rls_database):
    row = app_conn.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert row == (False, False), (
        f"Runtime role unexpectedly has elevated rights: rolsuper={row[0]}, "
        f"rolbypassrls={row[1]}"
    )


def test_app_role_cannot_disable_rls_on_protected_table(app_conn, rls_database):
    _expect_denied(
        app_conn,
        "ALTER TABLE indexed_content_items DISABLE ROW LEVEL SECURITY",
    )


def test_app_role_cannot_drop_existing_policy(app_conn, rls_database):
    _expect_denied(
        app_conn,
        "DROP POLICY indexed_content_items_rls ON indexed_content_items",
    )


def test_app_role_cannot_become_table_owner(app_conn, rls_database):
    # The owner role is whatever POSTGRES_USER is configured to — most often
    # 'postgres'. Either way, the app role must not be able to SET ROLE to it.
    _expect_denied(app_conn, "SET ROLE postgres")


def test_app_role_cannot_create_function_in_app_schema(app_conn, rls_database):
    _expect_denied(
        app_conn,
        "CREATE FUNCTION app.evil() RETURNS void AS $$ SELECT 1 $$ LANGUAGE sql",
    )


def test_app_role_cannot_read_pg_authid(app_conn, rls_database):
    """pg_authid contains password hashes and is restricted to superusers."""
    _expect_denied(app_conn, "SELECT rolname FROM pg_authid LIMIT 1")


def test_app_role_cannot_create_tables_in_public(app_conn, rls_database):
    """Creating a table would let an attacker bypass RLS on data they put in it."""
    _expect_denied(
        app_conn,
        "CREATE TABLE public.attacker_owned (id text PRIMARY KEY)",
    )
