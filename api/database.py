"""Database configuration using SQLAlchemy (Async)."""

import logging
from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import get_settings
from rls import internal_context, set_rls_context, user_context, worker_claim_context


logger = logging.getLogger(__name__)
settings = get_settings()


def build_postgres_url(*, async_driver: bool, owner: bool = False) -> str:
    """Build a SQLAlchemy/psycopg-compatible Postgres URL."""
    drivername = "postgresql+asyncpg" if async_driver else "postgresql"
    username = settings.POSTGRES_USER if owner else settings.POSTGRES_APP_USER
    password = settings.POSTGRES_PASSWORD if owner else settings.POSTGRES_APP_PASSWORD
    return URL.create(
        drivername=drivername,
        username=username,
        password=password,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
    ).render_as_string(hide_password=False)


DATABASE_URL = build_postgres_url(async_driver=True)
CHECKPOINTER_DATABASE_URL = build_postgres_url(async_driver=False)
CHECKPOINTER_SETUP_DATABASE_URL = build_postgres_url(async_driver=False, owner=True)


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


# --- Dependencies ---


def _request_context(request: Request):
    path = request.url.path
    if path.startswith("/api/auth/"):
        return internal_context("auth")
    if path.startswith("/api/worker/"):
        return worker_claim_context()
    user = getattr(request.state, "current_user", None)
    return user_context(user)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for DB session."""
    async with AsyncSessionLocal() as session:
        await set_rls_context(session, _request_context(request))
        yield session


async def init_db() -> None:
    """Verify database connectivity. Schema is managed by Alembic migrations."""
    async with engine.begin() as conn:
        from sqlalchemy import text
        from services.vector_dimensions import validate_database_vector_dimensions

        await conn.execute(text("SELECT 1"))
        await validate_database_vector_dimensions(conn, settings)
