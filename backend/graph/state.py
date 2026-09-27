"""
Shared LangGraph state.

Matches the Phase 1 AgentState design, plus a small number of disclosed
additions genuinely required to wire it to the FastAPI/MCP layers:

- number_of_questions: /quiz/start's request needs to tell Quiz Master how
  many questions to generate; the original template had nowhere to carry it.
- quiz_id: the Evaluator needs to know which stored quiz to grade.
- total_questions / percentage: separate from `score` (which is a raw count,
  matching the MCP save_progress contract's own `score`/`total_questions`
  split) rather than overloading one field for both a count and a percentage.
- awaiting_retry: the explicit flag route_after_evaluator/route_after_explainer
  use to distinguish "loop back into another quiz" from "standalone explain,
  end here" -- see graph/routing.py's module docstring for why this exists.
- error / source_type: needed by the FastAPI layer to build clean responses
  and error messages without re-deriving them from other fields.

All fields are optional (TypedDict total=False) since a single graph
invocation only ever populates the subset relevant to its path -- nodes
return partial dicts that LangGraph merges into the persisted state.
"""
from typing import Any, Optional

from typing_extensions import TypedDict


class Citation(TypedDict, total=False):
    source: str
    track: str
    subject: str
    document_name: str
    chapter: Optional[str]
    page: Optional[int]
    url: str  # present only for a web (Tavily) citation


class QuizQuestion(TypedDict, total=False):
    question_id: str
    question: str
    options: list[str]
    citation: dict


class AgentState(TypedDict, total=False):
    # identity / session
    student_id: str
    thread_id: str
    user_query: str

    # planner-derived
    learning_track: Optional[str]
    subject: Optional[str]
    topic: Optional[str]
    intent: Optional[str]
    difficulty: Optional[str]

    # RAG / explainer / ReAct
    retrieved_context: list[str]
    citations: list[dict]
    web_results: list[dict]
    react_iteration_count: int
    source_type: Optional[str]  # "KB" | "KB+WEB" | "WEB" | "NONE"

    # quiz / evaluation
    number_of_questions: Optional[int]
    quiz_id: Optional[str]
    quiz_questions: list[dict]
    student_answers: dict[str, str]

    score: Optional[float]
    total_questions: Optional[int]
    percentage: Optional[float]

    # The just-graded result, set once by the Evaluator and never touched by
    # any other node -- specifically NOT the same thing as score/percentage
    # above. Those two exist so the Planner can detect "an ungraded quiz is
    # pending" (state.get("score") is None) and are deliberately cleared by
    # Quiz Master every time it generates a fresh quiz (see
    # agents/quiz_master.py). When a retry chains evaluator -> explainer ->
    # quiz_master within one graph.ainvoke() call, that clearing would also
    # wipe out the very score the API response needs to report back to the
    # student for the submission that was just graded -- last_evaluation is
    # where the API layer (routes_quiz.py) reads it from instead.
    last_evaluation: Optional[dict]

    weak_topics: list[dict]

    # Explainer-only, additive (Tavily-based supplementary learning
    # resources -- videos/articles/real-world examples). Always the shape
    # {"videos": [...], "articles": [...], "real_world_examples": [...]};
    # never populated for a quiz/evaluate/revision invocation, only ever set
    # by explainer_node. See tools/tavily_tool.py:get_supplementary_resources.
    supplementary_resources: dict

    # feedback / adaptivity
    feedback: Optional[str]
    revision_plan: Optional[str]
    adaptive_loop_count: int
    awaiting_retry: bool

    # bookkeeping
    tool_results: dict[str, Any]
    final_answer: Optional[str]
    error: Optional[str]


def resume_with_answers(student_answers: dict[str, str]) -> dict:
    """
    The state update for a /quiz/submit-equivalent call on an existing
    thread_id -- deliberately NOT built from new_state(), which sets every
    field (including adaptive_loop_count, citations, weak_topics, ...) back
    to its blank default. Passing a full new_state() dict as the input to a
    resumed thread would silently reset adaptive_loop_count to 0 on every
    submission, defeating the adaptive retry limit entirely (caught while
    writing tests/test_graph.py, before it ever reached the API layer).

    `score` does not need to be reset here: agents/quiz_master.py already
    clears score/percentage/total_questions/student_answers every time it
    generates a fresh quiz, so by the time a submission arrives, `score` is
    already None in the checkpoint -- which is exactly what
    agents/planner.py's mid-quiz-resume detection depends on.
    """
    return {"student_answers": student_answers}


def new_state(
    *,
    student_id: str,
    thread_id: str,
    user_query: str,
    learning_track: Optional[str],
    subject: Optional[str],
    topic: Optional[str] = None,
    intent: Optional[str] = None,
    difficulty: Optional[str] = None,
    number_of_questions: Optional[int] = None,
    quiz_id: Optional[str] = None,
    student_answers: Optional[dict[str, str]] = None,
) -> AgentState:
    """Builds the initial state for one graph.ainvoke() call -- every field the Planner/router reads is set explicitly, nothing relies on a missing-key default."""
    return AgentState(
        student_id=student_id,
        thread_id=thread_id,
        user_query=user_query,
        learning_track=learning_track,
        subject=subject,
        topic=topic,
        intent=intent,
        difficulty=difficulty,
        retrieved_context=[],
        citations=[],
        web_results=[],
        react_iteration_count=0,
        source_type=None,
        number_of_questions=number_of_questions,
        quiz_id=quiz_id,
        quiz_questions=[],
        student_answers=student_answers or {},
        score=None,
        total_questions=None,
        percentage=None,
        last_evaluation=None,
        weak_topics=[],
        supplementary_resources={"videos": [], "articles": [], "real_world_examples": []},
        feedback=None,
        revision_plan=None,
        adaptive_loop_count=0,
        awaiting_retry=False,
        tool_results={},
        final_answer=None,
        error=None,
    )
