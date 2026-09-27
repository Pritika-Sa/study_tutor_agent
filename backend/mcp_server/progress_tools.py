"""
Progress tracking tools: save_progress, get_weak_topics, get_student_history,
get_topic_mastery, plus two additions beyond the required five --
save_revision_plan and get_latest_revision_plan. Both exist for the same
reason as quiz_tools.py's get_quiz_answer_key: the architecture's rule that
agents (and, here, FastAPI's /revision-plan route) never touch quiz/progress
persistence except through MCP would otherwise force the Revision Planner
agent to write revision_plans directly and the API layer to read it
directly. Adding these two keeps that rule absolute instead of carving out
an exception for one table.

Plain business logic, unit-testable directly; server.py wraps each
`*_impl` function with `@mcp.tool()`. Never imported by agents directly.

Mastery strategy (documented, as required)
-------------------------------------------
First attempt at a (track, subject, topic): mastery = this attempt's percentage.
Subsequent attempts: rolling average --
    new_mastery = (old_mastery * old_attempts + current_percentage) / (old_attempts + 1)
"""
import json
import logging
from typing import Optional

from config import settings
from database.database import SessionLocal
from database.models import QuizAttempt, RevisionPlan, TopicProgress
from rag.loader import validate_subject, validate_track

logger = logging.getLogger(__name__)


class ProgressToolError(RuntimeError):
    """An anticipated progress-tool failure (bad input)."""


def save_progress_impl(
    *,
    student_id: str,
    track: str,
    subject: str,
    topic: str,
    score: float,
    total_questions: int,
    timestamp: Optional[str] = None,
    weak_concepts: Optional[list[str]] = None,
) -> dict:
    validate_subject(track, subject)
    if total_questions <= 0:
        raise ProgressToolError("total_questions must be positive")
    if score < 0 or score > total_questions:
        raise ProgressToolError("score must be between 0 and total_questions")

    if weak_concepts:
        # The finalized Phase 2 schema's quiz_attempts/topic_progress tables
        # track exactly one topic per attempt -- there is no column for
        # sub-concept-level weak_concepts (that would be a schema change,
        # out of scope here). Logged for visibility, not silently dropped.
        logger.info("save_progress weak_concepts (informational only, not persisted): %s", weak_concepts)

    percentage = round((score / total_questions) * 100, 2)
    user_id = int(student_id)

    db = SessionLocal()
    try:
        attempt = QuizAttempt(
            user_id=user_id, track=track, subject=subject, topic=topic,
            score=score, total_questions=total_questions, percentage=percentage,
        )
        db.add(attempt)
        db.flush()  # populate attempt.id without committing yet

        progress = (
            db.query(TopicProgress)
            .filter_by(user_id=user_id, track=track, subject=subject, topic=topic)
            .first()
        )
        if progress is None:
            progress = TopicProgress(
                user_id=user_id, track=track, subject=subject, topic=topic,
                mastery=percentage, attempts=1,
            )
            db.add(progress)
        else:
            new_mastery = ((progress.mastery * progress.attempts) + percentage) / (progress.attempts + 1)
            progress.mastery = round(new_mastery, 2)
            progress.attempts += 1

        db.commit()
        db.refresh(attempt)
        db.refresh(progress)

        return {"status": "ok", "attempt_id": attempt.id, "mastery": progress.mastery}
    finally:
        db.close()


def get_weak_topics_impl(*, student_id: str, track: Optional[str] = None) -> dict:
    if track:
        validate_track(track)

    user_id = int(student_id)
    db = SessionLocal()
    try:
        query = db.query(TopicProgress).filter(
            TopicProgress.user_id == user_id,
            TopicProgress.mastery < settings.MASTERY_THRESHOLD_PERCENT,
        )
        if track:
            query = query.filter(TopicProgress.track == track)

        rows = query.order_by(TopicProgress.mastery.asc()).all()
        return {
            "weak_topics": [
                {"subject": r.subject, "topic": r.topic, "mastery": r.mastery, "attempts": r.attempts}
                for r in rows
            ]
        }
    finally:
        db.close()


def get_student_history_impl(*, student_id: str, track: Optional[str] = None, limit: int = 20) -> dict:
    if track:
        validate_track(track)
    if not (1 <= limit <= 200):
        raise ProgressToolError("limit must be between 1 and 200")

    user_id = int(student_id)
    db = SessionLocal()
    try:
        query = db.query(QuizAttempt).filter(QuizAttempt.user_id == user_id)
        if track:
            query = query.filter(QuizAttempt.track == track)

        rows = query.order_by(QuizAttempt.created_at.desc()).limit(limit).all()
        return {
            "attempts": [
                {
                    "track": r.track,
                    "subject": r.subject,
                    "topic": r.topic,
                    "score": r.score,
                    "total_questions": r.total_questions,
                    "percentage": r.percentage,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        }
    finally:
        db.close()


def get_topic_mastery_impl(*, student_id: str, track: str, subject: str, topic: str) -> dict:
    validate_subject(track, subject)

    user_id = int(student_id)
    db = SessionLocal()
    try:
        row = (
            db.query(TopicProgress)
            .filter_by(user_id=user_id, track=track, subject=subject, topic=topic)
            .first()
        )
        if row is None:
            return {"topic": topic, "mastery": 0.0, "attempts": 0}
        return {"topic": row.topic, "mastery": row.mastery, "attempts": row.attempts}
    finally:
        db.close()


def save_revision_plan_impl(*, student_id: str, track: str, plan: dict) -> dict:
    validate_track(track)
    db = SessionLocal()
    try:
        row = RevisionPlan(user_id=int(student_id), track=track, plan=json.dumps(plan))
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"status": "ok", "plan_id": row.id, "created_at": row.created_at.isoformat()}
    finally:
        db.close()


def get_latest_revision_plan_impl(*, student_id: str, track: Optional[str] = None) -> dict:
    if track:
        validate_track(track)

    user_id = int(student_id)
    db = SessionLocal()
    try:
        query = db.query(RevisionPlan).filter(RevisionPlan.user_id == user_id)
        if track:
            query = query.filter(RevisionPlan.track == track)

        row = query.order_by(RevisionPlan.created_at.desc()).first()
        if row is None:
            return {"plan": None}
        return {"plan": json.loads(row.plan), "created_at": row.created_at.isoformat(), "track": row.track}
    finally:
        db.close()
