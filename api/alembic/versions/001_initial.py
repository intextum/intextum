"""initial schema baseline for local development

Revision ID: 001
Revises:
Create Date: 2026-05-12

This is a squashed development-only baseline that materializes the current
SQLAlchemy models directly. Existing local databases from pre-squash revisions
are not upgrade-compatible and must be recreated.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

from config import get_settings
from models.sqlalchemy_models import Base

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


_SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "rls"


def _sql_literal(value: str) -> str:
    """Quote a value for inclusion as a Postgres string literal."""
    return "'" + value.replace("'", "''") + "'"


def _quoted_ident(value: str) -> str:
    """Quote a value as a Postgres identifier."""
    return '"' + value.replace('"', '""') + '"'


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)

    op.execute((_SQL_DIR / "010_helpers.sql").read_text())
    op.execute((_SQL_DIR / "020_policies.sql").read_text())

    settings = get_settings()
    app_user = settings.POSTGRES_APP_USER
    app_password = settings.POSTGRES_APP_PASSWORD
    role_sql = (
        (_SQL_DIR / "030_app_role.sql.tpl")
        .read_text()
        .replace("__APP_USER_SQL__", _sql_literal(app_user))
        .replace("__APP_PASSWORD_SQL__", _sql_literal(app_password))
        .replace("__APP_ROLE_IDENT__", _quoted_ident(app_user))
    )
    op.execute(role_sql)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
