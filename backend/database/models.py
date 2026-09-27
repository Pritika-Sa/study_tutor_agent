"""
ORM models for Phase 2.

Implements exactly the four tables defined in the Phase 1 schema:
users, quiz_attempts, topic_progress, revision_plans.

Track/subject values are stored as plain TEXT (not a DB-level enum) so the
schema stays compatible with the two-track architecture (NEET / Placement)
without hardcoding subject lists into the database layer -- validation of
allowed track/subject combinations belongs to the API layer added in later
phases, not to the schema.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    quiz_attempts = relationship("QuizAttempt", back_populates="user", cascade="all, delete-orphan")
    topic_progress = relationship("TopicProgress", back_populates="user", cascade="all, delete-orphan")
    revision_plans = relationship("RevisionPlan", back_populates="user", cascade="all, delete-orphan")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    track = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    total_questions = Column(Integer, nullable=False)
    percentage = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    user = relationship("User", back_populates="quiz_attempts")

    __table_args__ = (
        Index("idx_quiz_attempts_user_track_subject", "user_id", "track", "subject"),
    )


class TopicProgress(Base):
    __tablename__ = "topic_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    track = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    mastery = Column(Float, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="topic_progress")

    __table_args__ = (
        UniqueConstraint("user_id", "track", "subject", "topic", name="uq_topic_progress_user_track_subject_topic"),
        Index("idx_topic_progress_user_track", "user_id", "track"),
    )


class RevisionPlan(Base):
    __tablename__ = "revision_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    track = Column(String, nullable=False)
    plan = Column(String, nullable=False)  # JSON-encoded structured plan, stored as TEXT
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    user = relationship("User", back_populates="revision_plans")


class QuizRegistry(Base):
    """
    Server-side quiz answer key (Phase 4).

    Added to the same Phase 2 SQLite database -- not a new database. This is
    what makes /quiz/start -> /quiz/submit safe across two separate HTTP
    requests (and across a dev-server reload) without ever trusting the
    client with correct_option: the MCP generate_quiz tool writes one row
    here per generated quiz; the Evaluator agent reads it back by quiz_id
    through MCP get_quiz_answer_key, and it is never serialized into any
    API response.
    """
    __tablename__ = "quiz_registry"

    quiz_id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    track = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)
    questions_json = Column(String, nullable=False)  # JSON: full questions incl. correct_option + citation
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("idx_quiz_registry_user", "user_id"),
    )
