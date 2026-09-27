"""
Table creation for Phase 2.

Models must be imported before Base.metadata.create_all() runs, otherwise
SQLAlchemy has no knowledge of them. Importing database.models below (even
though nothing in this file references it directly) registers all four
tables on Base's metadata.
"""
from database.database import Base, engine
import database.models  # noqa: F401  (import needed for side effect: model registration)


def create_tables() -> None:
    """Create all Phase 2 tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)
