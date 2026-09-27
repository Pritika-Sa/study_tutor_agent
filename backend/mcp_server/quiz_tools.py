"""
Quiz generation + server-side answer key storage.

This module holds plain business logic (no MCP-protocol code) so it can be
unit-tested directly; backend/mcp_server/server.py wraps each `*_impl`
function with `@mcp.tool()`. Agents never import this module -- they reach
it only through backend/mcp_client/client.py -> MCP protocol -> server.py.

The answer key is persisted in the `quiz_registry` table (same Phase 2
SQLite database, see database/models.py: QuizRegistry) so it survives a
FastAPI dev-server reload between /quiz/start and /quiz/submit -- an
in-memory dict was the minimum the spec allowed, but a persisted row is not
meaningfully more complex and is considerably more robust.
"""
import json
import logging
import os
import uuid
from typing import Optional

from pydantic import BaseModel, Field, ValidationError, model_validator

from config import settings
from database.database import SessionLocal
from database.models import QuizRegistry
from rag.loader import validate_subject
from rag.retriever import retrieve

logger = logging.getLogger(__name__)

MAX_GENERATION_ATTEMPTS = 3  # bounded LLM/JSON-parsing retry count -- never unbounded
VALID_DIFFICULTIES = {"easy", "medium", "hard"}


class QuizToolError(RuntimeError):
    """An anticipated quiz-tool failure (bad input, insufficient RAG, generation failure)."""


class LLMGeneratedQuestion(BaseModel):
    """Validates one question the LLM returned before it is ever trusted."""
    question: str
    options: list[str] = Field(min_length=3, max_length=5)
    correct_option: str

    @model_validator(mode="after")
    def _correct_option_must_be_one_of_options(self) -> "LLMGeneratedQuestion":
        if self.correct_option not in self.options:
            raise ValueError("correct_option must exactly match one of the provided options")
        return self


def _call_groq_for_questions(*, context: str, subject: str, topic: str, difficulty: str, count: int) -> list[dict]:
    """
    Calls Groq to write `count` MCQs strictly grounded in `context`.

    Isolated in its own function specifically so tests can monkeypatch it
    with a deterministic stand-in. This environment has no live
    GROQ_API_KEY configured, so this exact function has not been exercised
    against the real Groq API -- see README "Known Limitations".

    Test seam: if MCP_TEST_FAKE_LLM_QUESTIONS is set (a JSON-encoded list of
    question dicts), it is returned directly instead of calling Groq. This
    is what lets backend/tests/test_mcp.py exercise the real MCP protocol
    round-trip (including this function's caller and everything downstream
    of it) without a live API key. It is never set outside test runs.
    """
    fake = os.environ.get("MCP_TEST_FAKE_LLM_QUESTIONS")
    if fake:
        return json.loads(fake)

    if not settings.GROQ_API_KEY:
        raise QuizToolError("GROQ_API_KEY is not configured -- cannot generate quiz questions.")

    from groq import Groq  # imported lazily: a missing/unused key never breaks module import

    client = Groq(api_key=settings.GROQ_API_KEY)
    prompt = (
        f"You are writing {difficulty} multiple-choice questions for the subject '{subject}', "
        f"topic '{topic}'. Base every question strictly on the CONTEXT below -- do not use "
        f"outside knowledge, and do not invent facts the context does not support. Return ONLY "
        f'a JSON array of exactly {count} objects, each with keys "question" (string), '
        f'"options" (array of exactly 4 strings), and "correct_option" (a string that exactly '
        f"matches one of the options).\n\nCONTEXT:\n{context}"
    )
    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    raw = response.choices[0].message.content
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array of questions from the LLM")
    return parsed


def generate_quiz_impl(
    *,
    student_id: str,
    track: str,
    subject: str,
    topic: str,
    difficulty: str,
    number_of_questions: int,
) -> dict:
    """Core logic behind the `generate_quiz` MCP tool. Raises QuizToolError/ValueError on any anticipated failure."""
    validate_subject(track, subject)  # raises ValueError for an unknown track or a track/subject mismatch

    if difficulty not in VALID_DIFFICULTIES:
        raise QuizToolError(f"Unknown difficulty '{difficulty}'. Valid values: {sorted(VALID_DIFFICULTIES)}")
    if not (1 <= number_of_questions <= 20):
        raise QuizToolError("number_of_questions must be between 1 and 20")

    # RAG grounding: topic-filtered first, then widen to the whole subject if that's too narrow.
    retrieval = retrieve(query=topic, track=track, subject=subject, topic=topic)
    if not retrieval.sufficient:
        retrieval = retrieve(query=topic, track=track, subject=subject, topic=None)

    if not retrieval.sufficient:
        raise QuizToolError(
            f"Insufficient source material to generate a grounded quiz for {track}/{subject}/{topic} "
            "-- refusing to fabricate questions."
        )

    context = "\n\n".join(doc.content for doc in retrieval.documents)
    # Simplification (documented): every question in a batch shares the single
    # best-scoring grounding citation, since generate_quiz grounds at
    # topic-level, not per-question. Finer per-question chunk attribution is
    # a possible future refinement, not implemented here.
    top_citation = retrieval.citations[0].model_dump()

    accepted: list[LLMGeneratedQuestion] = []
    last_error: Optional[str] = None
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        try:
            raw_questions = _call_groq_for_questions(
                context=context, subject=subject, topic=topic, difficulty=difficulty, count=number_of_questions,
            )
        except Exception as exc:  # noqa: BLE001 -- any LLM/parsing failure is just a retry-worthy attempt
            last_error = str(exc)
            logger.warning("Quiz generation attempt %d/%d failed: %s", attempt, MAX_GENERATION_ATTEMPTS, exc)
            continue

        accepted = []
        for raw in raw_questions:
            try:
                accepted.append(LLMGeneratedQuestion(**raw))
            except ValidationError as exc:
                logger.warning("Discarding malformed generated question: %s", exc)

        if len(accepted) >= number_of_questions:
            accepted = accepted[:number_of_questions]
            break

    if len(accepted) < number_of_questions:
        raise QuizToolError(
            f"Could not generate {number_of_questions} valid grounded question(s) after "
            f"{MAX_GENERATION_ATTEMPTS} attempts. Last error: {last_error}"
        )

    quiz_id = uuid.uuid4().hex
    full_questions = []   # includes correct_option -- server-side only, never returned from this function
    public_questions = []  # what generate_quiz returns to the caller

    for i, q in enumerate(accepted, start=1):
        question_id = f"q{i}"
        full_questions.append({
            "question_id": question_id,
            "question": q.question,
            "options": q.options,
            "correct_option": q.correct_option,
            "citation": top_citation,
        })
        public_questions.append({
            "question_id": question_id,
            "question": q.question,
            "options": q.options,
            "citation": top_citation,
        })

    db = SessionLocal()
    try:
        db.add(QuizRegistry(
            quiz_id=quiz_id,
            user_id=int(student_id),
            track=track,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            questions_json=json.dumps(full_questions),
        ))
        db.commit()
    finally:
        db.close()

    return {"quiz_id": quiz_id, "questions": public_questions}


def get_quiz_answer_key_impl(*, quiz_id: str, student_id: str) -> dict:
    """
    Server-side-only lookup of a previously generated quiz's full questions
    (including correct_option). Never exposed to the frontend -- the
    Evaluator agent is the only caller, via MCP, and only for its own quiz.
    """
    db = SessionLocal()
    try:
        row = db.query(QuizRegistry).filter(QuizRegistry.quiz_id == quiz_id).first()
        if row is None:
            raise QuizToolError(f"Unknown quiz_id '{quiz_id}'")
        if row.user_id != int(student_id):
            # User-isolation guardrail enforced at the MCP boundary too, not just in FastAPI.
            raise QuizToolError("This quiz does not belong to the requesting student")

        return {
            "quiz_id": row.quiz_id,
            "track": row.track,
            "subject": row.subject,
            "topic": row.topic,
            "difficulty": row.difficulty,
            "questions": json.loads(row.questions_json),
        }
    finally:
        db.close()
