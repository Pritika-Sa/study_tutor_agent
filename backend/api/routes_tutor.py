"""
POST /tutor/ask.

Routes through Planner -> Explainer (which internally runs the bounded
ReAct loop, falling back to Tavily only when RAG is insufficient). Every
request gets a fresh thread_id -- unlike the quiz flow, a single question
never needs to resume a previous one's checkpoint, so there is no reason to
risk stale state (old citations, old source_type) leaking across unrelated
questions on a shared thread.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from auth.auth import get_current_user
from database.models import User
from graph.state import new_state
from graph.workflow import get_graph_app

router = APIRouter(prefix="/tutor", tags=["Tutor"])


class AskRequest(BaseModel):
    track: str
    subject: str
    query: str = Field(min_length=1)
    topic: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    track: str
    subject: str
    topic: Optional[str] = None
    citations: list[dict]
    web_citations: list[dict] = []
    source_type: str
    # Backward-compatible addition: Tavily-based supplementary learning
    # resources (see tools/tavily_tool.py:get_supplementary_resources).
    # Always this shape, even when empty -- never omitted, so existing
    # clients that ignore unknown fields are unaffected and new clients
    # never need to null-check the key itself, only its three lists.
    supplementary_resources: dict = Field(
        default_factory=lambda: {"videos": [], "articles": [], "real_world_examples": []}
    )


@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, current_user: User = Depends(get_current_user)) -> AskResponse:
    thread_id = f"{current_user.id}:{payload.track}:{payload.subject}:ask:{uuid.uuid4().hex}"

    state = new_state(
        student_id=str(current_user.id),
        thread_id=thread_id,
        user_query=payload.query,
        learning_track=payload.track,
        subject=payload.subject,
        topic=payload.topic,
        intent="explain",
    )

    result = await get_graph_app().ainvoke(state, thread_id=thread_id)

    if result.get("intent") == "off_track":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("final_answer"))

    return AskResponse(
        answer=result.get("final_answer") or "",
        track=payload.track,
        subject=payload.subject,
        topic=result.get("topic"),
        citations=result.get("citations", []),
        web_citations=result.get("web_results", []),
        source_type=result.get("source_type") or "NONE",
        supplementary_resources=result.get("supplementary_resources")
        or {"videos": [], "articles": [], "real_world_examples": []},
    )
