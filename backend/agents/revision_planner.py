"""
Revision Planner Agent.

Uses MCP get_weak_topics, get_student_history, and get_topic_mastery (all
three, as required), then persists the generated plan via MCP
save_revision_plan -- never touches revision_plans (or any table) directly.
"""
import json
from datetime import datetime, timezone

from config import settings
from graph.state import AgentState
from mcp_client.client import MCPToolError, get_mcp_client


async def revision_planner_node(state: AgentState) -> dict:
    client = get_mcp_client()
    student_id = state["student_id"]
    track = state.get("learning_track")

    try:
        weak_result = await client.call_tool("get_weak_topics", {"student_id": student_id, "track": track})
        history_result = await client.call_tool(
            "get_student_history", {"student_id": student_id, "track": track, "limit": 10}
        )
    except MCPToolError as exc:
        return {"error": str(exc), "final_answer": None}

    weak_topics = weak_result["weak_topics"]
    plan_items = []
    for weak in weak_topics:
        try:
            detail = await client.call_tool("get_topic_mastery", {
                "student_id": student_id, "track": track, "subject": weak["subject"], "topic": weak["topic"],
            })
        except MCPToolError as exc:
            return {"error": str(exc), "final_answer": None}

        priority = "high" if detail["mastery"] < settings.MASTERY_THRESHOLD_PERCENT / 2 else "medium"
        plan_items.append({
            "subject": weak["subject"],
            "topic": weak["topic"],
            "mastery": detail["mastery"],
            "attempts": detail["attempts"],
            "priority": priority,
            "recommended_action": f"Review {weak['topic']} concepts before attempting again.",
            "suggested_practice": f"{'Focused' if priority == 'high' else 'Short'} practice set on {weak['topic']}.",
            "next_quiz_recommendation": f"Retake a {weak['subject']} quiz on {weak['topic']} once reviewed.",
        })

    plan = {
        "track": track,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weak_topics_considered": len(weak_topics),
        "recent_attempts_considered": len(history_result["attempts"]),
        "items": plan_items or [{"message": "No weak topics detected -- keep practicing to maintain mastery."}],
    }

    try:
        await client.call_tool("save_revision_plan", {"student_id": student_id, "track": track, "plan": plan})
    except MCPToolError as exc:
        return {"error": str(exc), "final_answer": None}

    return {
        "revision_plan": json.dumps(plan),
        "weak_topics": weak_topics,
        "final_answer": "Revision plan generated.",
        "error": None,
    }
