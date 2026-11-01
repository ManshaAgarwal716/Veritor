"""Database connection and session factory management."""

import logging
from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.base import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def normalize_database_url(url: str) -> str:
    """Normalize postgres URL schemes to psycopg if needed."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine(url: str | None = None) -> Engine | None:
    """Get or create the SQLAlchemy engine.

    Returns None if no database_url is provided and settings has no database_url.
    """
    global _engine, _session_factory
    target_url = url or get_settings().database_url
    if not target_url:
        return None

    if _engine is not None and str(_engine.url) == normalize_database_url(target_url):
        return _engine

    clean_url = normalize_database_url(target_url)
    connect_args: dict[str, Any] = {}
    if clean_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    try:
        _engine = create_engine(
            clean_url,
            connect_args=connect_args,
            pool_pre_ping=True,
            echo=False,
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
        return _engine
    except Exception as exc:
        logger.warning("Failed to initialize database engine for %s: %s", clean_url, exc)
        return None


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session] | None:
    """Get the session factory for the configured engine."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory
    eng = engine or get_engine()
    if eng is None:
        return None
    _session_factory = sessionmaker(bind=eng, expire_on_commit=False)
    return _session_factory


def init_db(engine: Engine | None = None) -> bool:
    """Create all tables in the target database.

    Useful for development, tests, or initial startup without Alembic.
    Returns True if initialized, False if no engine is configured.
    """
    eng = engine or get_engine()
    if eng is None:
        return False
    try:
        Base.metadata.create_all(bind=eng)
        logger.info("Database tables initialized successfully on %s", eng.url)
        return True
    except Exception as exc:
        logger.warning("Failed to initialize database tables on %s: %s", eng.url, exc)
        return False


def get_db_session() -> Generator[Session | None, None, None]:
    """Dependency provider yielding a Session if database is configured, or None."""
    factory = get_session_factory()
    if factory is None:
        yield None
        return

    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
