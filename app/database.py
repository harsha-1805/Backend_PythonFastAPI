"""
Database engine and session management.

Engine is created from `settings.database_url` (read from .env).
`pool_pre_ping=True` so stale/dropped connections (common with Postgres
after idle periods) are detected and replaced automatically instead of
surfacing as random request failures.

SQLite needs `check_same_thread=False` because FastAPI runs sync path
operations in a worker thread pool, and SQLite's default driver
otherwise refuses to reuse a connection created on a different thread.
Postgres (and other real DB servers) don't need this, so it's only
applied when the URL is a sqlite:// URL.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()