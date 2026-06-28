from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.shared.config import get_settings
from services.shared.models import Base


def _sync_database_url(url: str | None = None) -> str:
    settings = get_settings()
    raw = url or settings.database_url
    if raw.startswith("postgresql+asyncpg://"):
        return raw.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    return raw


def create_sync_engine(database_url: str | None = None):
    return create_engine(_sync_database_url(database_url), pool_pre_ping=True)


def create_session_factory(engine=None) -> sessionmaker[Session]:
    if engine is None:
        engine = create_sync_engine()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session] | None = None,
) -> Generator[Session, None, None]:
    factory = session_factory or create_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine=None) -> None:
    if engine is None:
        engine = create_sync_engine()
    Base.metadata.create_all(bind=engine)
