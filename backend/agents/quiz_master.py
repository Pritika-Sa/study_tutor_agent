"""
Quiz Master Agent.

Calls MCP `generate_quiz` through the MCP client only -- never imports
mcp_server/quiz_tools.py and never touches the database directly. Returns
whatever the MCP tool returned, which already excludes correct_option.
"""
from graph.state import AgentState
from mcp_client.client import MCPToolError, get_mcp_client


async def quiz_master_node(state: AgentState) -> dict:
    client = get_mcp_client()
    try:
        result = await client.call_tool("generate_quiz", {
            "student_id": state["student_id"],
            "track": state["learning_track"],
            "subject": state["subject"],
            "topic": state.get("topic") or state["subject"],
            "difficulty": state.get("difficulty") or "medium",
            "number_of_questions": state.get("number_of_questions") or 5,
        })
    except MCPToolError as exc:
        return {"quiz_id": None, "quiz_questions": [], "error": str(exc), "final_answer": None}

    return {
        "quiz_id": result["quiz_id"],
        "quiz_questions": result["questions"],
        # A freshly generated quiz has no score yet -- explicitly clear these
        # rather than leaving a previous attempt's values in the checkpoint
        # (this is what makes the Planner's mid-quiz-resume detection
        # ("student_answers present AND score is None") correct even inside
        # the adaptive retry loop, where Evaluator -> Explainer -> QuizMaster
        # all run within one invocation and would otherwise leave the first
        # attempt's score/answers lingering in the persisted state).
        "score": None,
        "percentage": None,
        "total_questions": None,
        "student_answers": {},
        "error": None,
    }
