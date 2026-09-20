from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def configure_database(url: str | None = None) -> Engine:
    """Configure the process-wide SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal
    database_url = url or settings.database_url
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    _engine = create_engine(database_url, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    """Return the configured engine, creating it from settings when needed."""
    if _engine is None:
        return configure_database()
    return _engine


def get_session() -> Iterator[Session]:
    """Yield a request-scoped database session."""
    global _SessionLocal
    if _SessionLocal is None:
        configure_database()
    if _SessionLocal is None:  # pragma: no cover - defensive type narrowing
        raise RuntimeError("Database session factory was not configured")
    with _SessionLocal() as session:
        yield session


def run_migrations(database_url: str) -> None:
    """Upgrade the database at ``database_url`` to the latest schema."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["database_url_override"] = database_url
    command.upgrade(config, "head")


def init_db() -> None:
    """Upgrade the currently configured database.

    Kept as a compatibility entry point for existing maintenance scripts.
    """
    run_migrations(str(get_engine().url))


def new_session() -> Session:
    """Create a caller-managed database session."""
    global _SessionLocal
    if _SessionLocal is None:
        configure_database()
    if _SessionLocal is None:  # pragma: no cover - defensive type narrowing
        raise RuntimeError("Database session factory was not configured")
    return _SessionLocal()
