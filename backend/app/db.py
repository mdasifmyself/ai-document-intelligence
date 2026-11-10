"""Database engine, session helper and schema creation."""
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine():
    """Used by tests to point at a different database."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine, _SessionLocal = None, None


@contextmanager
def session_scope():
    engine()
    s: Session = _SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db():
    """FastAPI dependency."""
    engine()
    s: Session = _SessionLocal()
    try:
        yield s
    finally:
        s.close()


def init_db():
    """Create extensions and tables. Idempotent, runs at API and worker start."""
    from . import models  # noqa: F401  (registers tables)

    eng = engine()
    with eng.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))  # api + workers may start together
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        Base.metadata.create_all(conn)
        # small forward-only migrations for databases created by an earlier version
        conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz"))
