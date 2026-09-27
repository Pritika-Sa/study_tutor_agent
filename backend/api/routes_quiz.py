"""
POST /quiz/start, POST /quiz/submit.

Quiz answers are graded strictly server-side via the MCP answer key
(agents/evaluator.py) -- this layer never accepts or trusts a client-
supplied score, correctness, or student_id (student_id always comes from
the authenticated JWT, never the request body).

thread_id for the quiz flow is deterministic: f"{user_id}:{track}:{subject}"
(matching the Phase 1 architecture's own suggestion), because /quiz/start
and /quiz/submit are two separate HTTP requests that must resume the same
LangGraph checkpoint. Known simplification, documented rather than hidden:
this means one *active* (started-but-not-yet-submitted) quiz per
(student, track, subject) at a time -- starting a second quiz on the same
subject before submitting the first resumes/overwrites that same thread.
Acceptable at capstone scale; a real product would key threads by quiz
session instead.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from auth.auth import get_current_user
from database.models import User
from graph.state import new_state, resume_with_answers
from graph.workflow import get_graph_app
from mcp_client.client import MCPToolError, get_mcp_client

router = APIRouter(prefix="/quiz", tags=["Quiz"])


def _thread_id_for_quiz(user_id: int, track: str, subject: str) -> str:
    return f"{user_id}:{track}:{subject}"


class QuizStartRequest(BaseModel):
    track: str
    subject: str
    topic: str
    difficulty: str = "medium"
    number_of_questions: int = Field(default=5, ge=1, le=20)


class QuizStartResponse(BaseModel):
    quiz_id: str
    track: str
    subject: str
    topic: str
    questions: list[dict]  # never includes correct_option -- see mcp_server/quiz_tools.py


class QuizSubmitRequest(BaseModel):
    quiz_id: str
    answers: dict[str, str]  # question_id -> letter ("A", "B", ...), see agents/evaluator.py


class QuizSubmitResponse(BaseModel):
    score: float
    total_questions: int
    percentage: float
    weak_topics: list[dict]
    feedback: str
    next_action: str


@router.post("/start", response_model=QuizStartResponse)
async def start_quiz(payload: QuizStartRequest, current_user: User = Depends(get_current_user)) -> QuizStartResponse:
    thread_id = _thread_id_for_quiz(current_user.id, payload.track, payload.subject)

    state = new_state(
        student_id=str(current_user.id),
        thread_id=thread_id,
        user_query="",
        learning_track=payload.track,
        subject=payload.subject,
        topic=payload.topic,
        intent="quiz",
        difficulty=payload.difficulty,
        number_of_questions=payload.number_of_questions,
    )

    result = await get_graph_app().ainvoke(state, thread_id=thread_id)

    if result.get("intent") == "off_track":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("final_answer"))
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    if not result.get("quiz_id"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Quiz generation failed unexpectedly")

    return QuizStartResponse(
        quiz_id=result["quiz_id"],
        track=payload.track,
        subject=payload.subject,
        topic=payload.topic,
        questions=result["quiz_questions"],
    )


@router.post("/submit", response_model=QuizSubmitResponse)
async def submit_quiz(payload: QuizSubmitRequest, current_user: User = Depends(get_current_user)) -> QuizSubmitResponse:
    # track/subject aren't in the request contract (only quiz_id + answers) --
    # looked up via the MCP-scoped quiz registry rather than trusted from the
    # client, and scoped to this student (get_quiz_answer_key enforces that).
    client = get_mcp_client()
    try:
        answer_key = await client.call_tool(
            "get_quiz_answer_key", {"quiz_id": payload.quiz_id, "student_id": str(current_user.id)}
        )
    except MCPToolError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    thread_id = _thread_id_for_quiz(current_user.id, answer_key["track"], answer_key["subject"])

    result = await get_graph_app().ainvoke(resume_with_answers(payload.answers), thread_id=thread_id)

    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])

    evaluation = result.get("last_evaluation")
    if not evaluation:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Evaluation failed unexpectedly")

    return QuizSubmitResponse(
        score=evaluation["score"],
        total_questions=evaluation["total_questions"],
        percentage=evaluation["percentage"],
        weak_topics=evaluation["weak_topics"],
        feedback=evaluation["feedback"],
        next_action=evaluation["next_action"],
    )
