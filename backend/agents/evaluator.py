"""
Evaluator Agent.

Grades strictly server-side: the answer key comes from MCP
`get_quiz_answer_key` (never trusts a client-supplied score/correctness),
then calls MCP `save_progress` and `get_weak_topics`. Never imports
mcp_server/*.py or the database directly.

Answer format: /quiz/submit's student_answers map question_id -> a letter
("A", "B", ...), matching the position of that question's `options` list
(the public quiz payload has no letters attached -- the frontend assigns
them positionally when it renders the options). This mapping is a Phase 4/7
design decision, not given verbatim in the brief, so it's documented here
explicitly.
"""
import logging
from datetime import datetime, timezone

from config import settings
from graph.state import AgentState
from mcp_client.client import MCPToolError, get_mcp_client

logger = logging.getLogger(__name__)

_LETTER_TO_INDEX = {chr(ord("A") + i): i for i in range(10)}


def _grade(questions: list[dict], student_answers: dict[str, str]) -> tuple[int, int]:
    correct = 0
    total = len(questions)
    for question in questions:
        letter = (student_answers.get(question["question_id"]) or "").strip().upper()
        idx = _LETTER_TO_INDEX.get(letter)
        if idx is not None and 0 <= idx < len(question["options"]) and question["options"][idx] == question["correct_option"]:
            correct += 1
    return correct, total


def _weakest_topic(weak_topics: list[dict], fallback: str) -> str:
    return weak_topics[0]["topic"] if weak_topics else fallback


async def evaluator_node(state: AgentState) -> dict:
    quiz_id = state.get("quiz_id")
    student_answers = state.get("student_answers") or {}
    student_id = state["student_id"]

    client = get_mcp_client()

    try:
        answer_key = await client.call_tool("get_quiz_answer_key", {"quiz_id": quiz_id, "student_id": student_id})
    except MCPToolError as exc:
        return {"error": str(exc), "final_answer": None}

    questions = answer_key["questions"]
    correct, total = _grade(questions, student_answers)
    percentage = round((correct / total) * 100, 2) if total else 0.0

    weak_concepts = [answer_key["topic"]] if percentage < settings.MASTERY_THRESHOLD_PERCENT else []

    try:
        await client.call_tool("save_progress", {
            "student_id": student_id,
            "track": answer_key["track"],
            "subject": answer_key["subject"],
            "topic": answer_key["topic"],
            "score": correct,
            "total_questions": total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "weak_concepts": weak_concepts,
        })
        weak_topics_result = await client.call_tool(
            "get_weak_topics", {"student_id": student_id, "track": answer_key["track"]}
        )
    except MCPToolError as exc:
        return {"error": str(exc), "final_answer": None}

    weak_topics = weak_topics_result["weak_topics"]

    # Adaptive routing decision -- see graph/routing.py for how awaiting_retry is consumed.
    loop_count = state.get("adaptive_loop_count", 0)
    if percentage >= settings.MASTERY_THRESHOLD_PERCENT:
        awaiting_retry = False
    elif loop_count >= settings.ADAPTIVE_MAX_RETRIES:
        awaiting_retry = False  # retries exhausted -- forced stop, guardrail against an uncontrolled loop
    else:
        awaiting_retry = True
        loop_count += 1

    if awaiting_retry:
        next_topic = _weakest_topic(weak_topics, fallback=answer_key["topic"])
        feedback = (
            f"You scored {correct}/{total} ({percentage}%) on {answer_key['topic']} -- below the "
            f"{settings.MASTERY_THRESHOLD_PERCENT}% mastery threshold. Re-explaining {next_topic}, then a new quiz."
        )
    else:
        next_topic = answer_key["topic"]
        outcome = "reached the mastery threshold" if percentage >= settings.MASTERY_THRESHOLD_PERCENT else "used all retry attempts"
        feedback = f"You scored {correct}/{total} ({percentage}%) on {answer_key['topic']} and {outcome}. Moving to your revision plan."

    last_evaluation = {
        "score": correct,
        "total_questions": total,
        "percentage": percentage,
        "feedback": feedback,
        "weak_topics": weak_topics,
        "next_action": "retry_quiz" if awaiting_retry else "revision",
    }

    result = {
        "score": correct,
        "total_questions": total,
        "percentage": percentage,
        "last_evaluation": last_evaluation,
        "weak_topics": weak_topics,
        "feedback": feedback,
        "adaptive_loop_count": loop_count,
        "awaiting_retry": awaiting_retry,
        "learning_track": answer_key["track"],
        "subject": answer_key["subject"],
        "topic": next_topic,
        "error": None,
    }

    if awaiting_retry:
        # Quiz flows never populate a natural-language user_query (there is
        # no question text for a quiz-start request), but the retry loop
        # sends this same state straight into the Explainer node next. Give
        # it something real to work with instead of leaving the empty
        # string from the original /quiz/start call -- caught via a live
        # Tavily 400 ("Query is missing.") once TAVILY_API_KEY was
        # configured for real; an empty query was silently "fine" against
        # the stubbed test double, but the real API correctly rejects it.
        result["user_query"] = f"Explain {next_topic}"

    return result
