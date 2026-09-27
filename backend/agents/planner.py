"""
Planner Agent.

Scope decision (disclosed): the FastAPI API design (Phase 7) has each
endpoint's request body already carry `track` + `subject` explicitly (and
`/quiz/start` carries `topic` too), and the endpoint called already fixes
the intent (/tutor/ask -> explain, /quiz/start -> quiz, /revision-plan ->
revision). So the Planner's real job is NOT freeform NLU over raw text --
it's the deterministic part every one of those requests still needs:

1. Enforce the track/subject guardrail (reusing rag/loader.py's validator --
   the same one RAG/MCP already use, so "off-track" means the exact same
   thing everywhere in the system). Revision-plan requests span a whole
   track rather than one subject, so when subject is None (only ever true
   for intent="revision"), just the track itself is validated instead.
2. Default a missing difficulty to "medium".
3. Detect the mid-quiz resume case: /quiz/submit re-enters the SAME
   checkpointed thread with student_answers populated and no score yet, so
   the Planner routes straight to the Evaluator regardless of whatever
   intent the caller passed in.

Freeform "classify this sentence into track+subject+intent" NLU is a
plausible future enhancement but is not implemented here -- doing it
convincingly needs an LLM call this environment cannot verify live (no
GROQ_API_KEY configured), and claiming it works would be exactly the kind
of unverified claim this project's instructions rule out.
"""
from typing import Optional

from graph.state import AgentState
from rag.loader import validate_subject, validate_track

VALID_INTENTS = {"explain", "quiz", "evaluate", "revision"}


def planner_node(state: AgentState) -> dict:
    track = state.get("learning_track")
    subject = state.get("subject")
    intent = state.get("intent")

    try:
        if subject is not None:
            validate_subject(track, subject)
        else:
            validate_track(track)
    except ValueError as exc:
        return {
            "intent": "off_track",
            "final_answer": (
                f"'{subject}' is not part of your selected {track} track. "
                "Please choose a subject from your selected track instead."
            ) if subject is not None else f"'{track}' is not a recognized learning track.",
            "error": str(exc),
        }

    # Resume case: /quiz/submit re-enters this thread with answers already
    # present and no score yet -- always route to the Evaluator for that,
    # no matter what intent the request nominally carried.
    if state.get("student_answers") and state.get("score") is None:
        intent = "evaluate"

    if intent not in VALID_INTENTS:
        return {
            "intent": "off_track",
            "final_answer": f"Unrecognized request type '{intent}'.",
            "error": f"invalid intent '{intent}'",
        }

    difficulty: Optional[str] = state.get("difficulty") or "medium"

    return {"intent": intent, "difficulty": difficulty, "error": None}
