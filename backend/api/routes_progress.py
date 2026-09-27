"""
GET /progress, GET /weak-topics, GET /revision-plan, GET /history, GET /tracks.

Every route below (aside from /tracks, which is static) reaches quiz/
progress data only through the MCP client -- never a direct database query
-- and student_id always comes from the authenticated JWT (get_current_user),
never from a request parameter, so one student can never read another's data.
"""
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from auth.auth import get_current_user
from config import settings
from database.models import User
from graph.state import new_state
from graph.workflow import get_graph_app
from mcp_client.client import MCPToolError, get_mcp_client
from rag.loader import TRACK_SUBJECTS

router = APIRouter(tags=["Progress"])


def _weak_topics_snapshot(weak_topics: list[dict]) -> set[tuple]:
    """(subject, topic, mastery, attempts) per weak topic -- changes if the
    topic set changes OR an existing weak topic's mastery/attempts move
    (e.g. a second low-score attempt updates mastery but the topic was
    already weak), not just if the set of topics is identical."""
    return {(w["subject"], w["topic"], w["mastery"], w["attempts"]) for w in weak_topics}


def _plan_snapshot(plan: dict) -> set[tuple]:
    # A plan with no weak topics stores a single {"message": ...} placeholder
    # item (see agents/revision_planner.py) instead of real topic entries --
    # skip it here so an empty plan's snapshot is correctly the empty set,
    # matching _weak_topics_snapshot([]) rather than crashing on a missing key.
    return {
        (item["subject"], item["topic"], item["mastery"], item["attempts"])
        for item in plan.get("items", [])
        if "topic" in item
    }


@router.get("/tracks")
async def get_tracks(current_user: User = Depends(get_current_user)) -> dict:
    return {track: sorted(subjects) for track, subjects in TRACK_SUBJECTS.items()}


@router.get("/weak-topics")
async def get_weak_topics_route(track: Optional[str] = None, current_user: User = Depends(get_current_user)) -> dict:
    client = get_mcp_client()
    try:
        return await client.call_tool("get_weak_topics", {"student_id": str(current_user.id), "track": track})
    except MCPToolError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/history")
async def get_history_route(
    track: Optional[str] = None, limit: int = 20, current_user: User = Depends(get_current_user)
) -> dict:
    client = get_mcp_client()
    try:
        return await client.call_tool(
            "get_student_history", {"student_id": str(current_user.id), "track": track, "limit": limit}
        )
    except MCPToolError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/progress")
async def get_progress_route(track: Optional[str] = None, current_user: User = Depends(get_current_user)) -> dict:
    client = get_mcp_client()
    student_id = str(current_user.id)
    try:
        weak = await client.call_tool("get_weak_topics", {"student_id": student_id, "track": track})
        recent = await client.call_tool("get_student_history", {"student_id": student_id, "track": track, "limit": 20})
    except MCPToolError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    attempts = recent["attempts"]
    overall_percentage = round(sum(a["percentage"] for a in attempts) / len(attempts), 2) if attempts else 0.0

    # "Strong topics": the most recent attempt on each (subject, topic) that
    # scored at/above the mastery threshold. Derived here from attempt
    # history (already available) rather than adding a dedicated MCP tool
    # for it -- get_weak_topics covers the below-threshold side using the
    # rolling-average mastery figure; this is a distinct, disclosed
    # definition for the complementary "strong" side, not the same number.
    latest_by_topic: dict[tuple, dict] = {}
    for attempt in attempts:  # newest-first, per get_student_history's contract
        key = (attempt["subject"], attempt["topic"])
        latest_by_topic.setdefault(key, attempt)
    strong_topics = [
        {"subject": subject, "topic": topic, "percentage": attempt["percentage"]}
        for (subject, topic), attempt in latest_by_topic.items()
        if attempt["percentage"] >= settings.MASTERY_THRESHOLD_PERCENT
    ]

    return {
        "track": track,
        "overall_percentage": overall_percentage,
        "recent_attempts": attempts,
        "weak_topics": weak["weak_topics"],
        "strong_topics": strong_topics,
    }


@router.get("/revision-plan")
async def get_revision_plan_route(track: Optional[str] = None, current_user: User = Depends(get_current_user)) -> dict:
    client = get_mcp_client()
    student_id = str(current_user.id)

    try:
        existing = await client.call_tool("get_latest_revision_plan", {"student_id": student_id, "track": track})
    except MCPToolError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if existing.get("plan") is not None:
        # A saved plan existing is not the same as it being current: the
        # LangGraph adaptive loop only reaches revision_planner_node when a
        # quiz's retry loop actually concludes (passes threshold or exhausts
        # ADAPTIVE_MAX_RETRIES -- see graph/routing.py / README section 6),
        # not on every quiz attempt. A student can pick up brand-new weak
        # topics (or a mastery/attempts change on an existing one) via
        # quizzes that never reach that node, leaving whatever plan was last
        # saved returned here forever even though topic_progress has since
        # moved on. Compare the saved plan's own weak-topic snapshot against
        # a fresh MCP get_weak_topics call (the same live source
        # revision_planner_node itself always uses) and only trust the cache
        # when nothing has actually changed -- this is a currency check
        # against the backend's own existing data, not a second revision
        # algorithm; the regenerated plan still comes entirely from
        # revision_planner_node below.
        if track:
            try:
                current_weak = await client.call_tool("get_weak_topics", {"student_id": student_id, "track": track})
            except MCPToolError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

            if _plan_snapshot(existing["plan"]) == _weak_topics_snapshot(current_weak["weak_topics"]):
                return existing
            # else: fall through and regenerate -- the plan is stale.
        else:
            # No specific track requested: `existing` is just the single
            # most-recently-created plan across all of this student's
            # tracks (see get_latest_revision_plan_impl), and there is no
            # single "current weak topics" list to compare it against
            # without knowing which track to regenerate for. Same as the
            # pre-existing behavior.
            return existing

    if not track:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No revision plan exists yet -- pass ?track= to generate one for a specific track.",
        )

    thread_id = f"{current_user.id}:{track}:revision:{uuid.uuid4().hex}"
    state = new_state(
        student_id=student_id, thread_id=thread_id, user_query="",
        learning_track=track, subject=None, intent="revision",
    )
    result = await get_graph_app().ainvoke(state, thread_id=thread_id)

    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])

    return {"plan": json.loads(result["revision_plan"]), "track": track}
