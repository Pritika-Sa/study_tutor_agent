"""
SQLAlchemy engine/session setup.

This module is intentionally framework-agnostic (no FastAPI imports besides
the get_db dependency generator) so it can be reused as-is by both the
FastAPI backend and the future MCP server process, which both need to read
and write the same SQLite database.
"""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

# SQLite requires this flag when the same connection may be touched by more
# than one thread (FastAPI can service requests on different worker threads).
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

# Built from the resolved absolute path (not the raw DATABASE_URL string) so
# this engine and graph/workflow.py's LangGraph checkpointer are guaranteed
# to open the same file regardless of the process's current working
# directory -- see Settings.sqlite_file_path's docstring.
_engine_url = f"sqlite:///{settings.sqlite_file_path}" if _is_sqlite else settings.DATABASE_URL

engine = create_engine(_engine_url, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
