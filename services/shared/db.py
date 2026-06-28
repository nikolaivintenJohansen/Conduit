from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from services.shared.config import get_settings
from services.shared.models import Base

_sync_engine: Engine | None = None
_async_engine: AsyncEngine | None = None
_session_factory: sessionmaker[Session] | None = None


def _normalize_sync_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def _normalize_async_url(database_url: str) -> str:
    url = _normalize_sync_url(database_url)
    if "+psycopg" in url:
        return url.replace("+psycopg", "+asyncpg", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def create_db_engine(database_url: str | None = None) -> Engine:
    """Sync SQLAlchemy engine for ORM sessions and tests."""
    global _sync_engine
    url = _normalize_sync_url(database_url or get_settings().database_url)
    if _sync_engine is None:
        _sync_engine = create_engine(url, pool_pre_ping=True)
    return _sync_engine


def init_db(engine: Engine) -> None:
    """Create ORM tables (tests); production uses SQL migrations."""
    Base.metadata.create_all(bind=engine)


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=engine or create_db_engine(),
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_async_engine(database_url: str | None = None) -> AsyncEngine:
    global _async_engine
    url = _normalize_async_url(database_url or get_settings().database_url)
    if _async_engine is None:
        _async_engine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _async_engine


async def check_database(database_url: str | None = None) -> bool:
    engine = get_async_engine(database_url)
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def dispose_engine() -> None:
    global _sync_engine, _async_engine, _session_factory
    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None
    _session_factory = None
