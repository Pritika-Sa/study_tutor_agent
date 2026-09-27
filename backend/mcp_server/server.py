"""
Custom MCP server (Phase 4).

Runs as a SEPARATE PROCESS over stdio transport (mcp_client/client.py
launches this file with the same Python interpreter and talks to it via the
MCP protocol -- it is never imported directly). Exposes six tools: the five
required by the architecture plus get_quiz_answer_key, which the Evaluator
agent needs so it never has to import quiz_tools.py itself (see that
module's docstring for why this exists).

Anticipated failures (bad track/subject, insufficient RAG, unknown quiz_id,
etc.) are re-raised as `ToolError` so the real message reaches the caller;
anything else is treated by the MCP SDK as a genuine crash (masked message,
full traceback logged server-side only) -- see mcp.server.mcpserver.exceptions.ToolError's
docstring for this distinction.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from mcp_server import progress_tools, quiz_tools  # noqa: E402

mcp = MCPServer("adaptive-study-tutor")


@mcp.tool()
def generate_quiz(
    student_id: str,
    track: str,
    subject: str,
    topic: str,
    difficulty: str,
    number_of_questions: int,
) -> dict:
    """Generate a source-grounded quiz for a track/subject/topic. Returns questions WITHOUT correct answers."""
    try:
        return quiz_tools.generate_quiz_impl(
            student_id=student_id,
            track=track,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            number_of_questions=number_of_questions,
        )
    except (quiz_tools.QuizToolError, ValueError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def get_quiz_answer_key(quiz_id: str, student_id: str) -> dict:
    """Server-side only: return a previously generated quiz's full questions (incl. correct_option), scoped to the requesting student."""
    try:
        return quiz_tools.get_quiz_answer_key_impl(quiz_id=quiz_id, student_id=student_id)
    except quiz_tools.QuizToolError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def save_progress(
    student_id: str,
    track: str,
    subject: str,
    topic: str,
    score: float,
    total_questions: int,
    timestamp: str | None = None,
    weak_concepts: list[str] | None = None,
) -> dict:
    """Persist a quiz attempt and update the student's rolling topic mastery."""
    try:
        return progress_tools.save_progress_impl(
            student_id=student_id,
            track=track,
            subject=subject,
            topic=topic,
            score=score,
            total_questions=total_questions,
            timestamp=timestamp,
            weak_concepts=weak_concepts,
        )
    except (progress_tools.ProgressToolError, ValueError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def get_weak_topics(student_id: str, track: str | None = None) -> dict:
    """Return this student's topics with mastery below MASTERY_THRESHOLD_PERCENT, weakest first."""
    try:
        return progress_tools.get_weak_topics_impl(student_id=student_id, track=track)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def get_student_history(student_id: str, track: str | None = None, limit: int = 20) -> dict:
    """Return this student's recent quiz attempts, newest first."""
    try:
        return progress_tools.get_student_history_impl(student_id=student_id, track=track, limit=limit)
    except (progress_tools.ProgressToolError, ValueError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def get_topic_mastery(student_id: str, track: str, subject: str, topic: str) -> dict:
    """Return this student's mastery percentage + attempt count for one topic (0/0 if never attempted)."""
    try:
        return progress_tools.get_topic_mastery_impl(student_id=student_id, track=track, subject=subject, topic=topic)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def save_revision_plan(student_id: str, track: str, plan: dict) -> dict:
    """Persist a generated revision plan for this student."""
    try:
        return progress_tools.save_revision_plan_impl(student_id=student_id, track=track, plan=plan)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def get_latest_revision_plan(student_id: str, track: str | None = None) -> dict:
    """Return this student's most recently generated revision plan, or {"plan": null} if none exists yet."""
    try:
        return progress_tools.get_latest_revision_plan_impl(student_id=student_id, track=track)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
