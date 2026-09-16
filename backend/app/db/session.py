from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base

_engine = None
_SessionLocal = None


def configure_database(url: str | None = None):
    global _engine, _SessionLocal
    db_url = url or settings.database_url
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    _engine = create_engine(db_url, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine():
    global _engine
    if _engine is None:
        configure_database()
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        configure_database()
    with _SessionLocal() as session:
        yield session


def init_db() -> None:
    Base.metadata.create_all(get_engine())


def new_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        configure_database()
    return _SessionLocal()
