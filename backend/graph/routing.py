"""
Conditional routing for the LangGraph workflow.

Two independent routing decisions, each reading one explicit state signal
(neither infers the other's decision from context):

- route_after_planner: dispatches on `intent`, which the Planner has already
  resolved (including its off-track guardrail and mid-quiz-resume detection).
- route_after_evaluator / route_after_explainer: both read the single
  `awaiting_retry` flag the Evaluator computes, so "loop back for a retry"
  vs. "standalone explain, end here" is one explicit signal shared by both
  routers, not two routing functions independently guessing the same thing.
"""
from langgraph.graph import END

from graph.state import AgentState

INTENT_TO_NODE = {
    "explain": "explainer",
    "quiz": "quiz_master",
    "evaluate": "evaluator",
    "revision": "revision_planner",
}


def route_after_planner(state: AgentState) -> str:
    intent = state.get("intent")
    if intent == "off_track":
        return "off_track_reply"
    return INTENT_TO_NODE.get(intent, "off_track_reply")


def route_after_evaluator(state: AgentState) -> str:
    return "explainer" if state.get("awaiting_retry") else "revision_planner"


def route_after_explainer(state: AgentState):
    # awaiting_retry is only ever set True by the Evaluator -- a standalone
    # "explain" intent never touches it, so this is falsy/absent there and
    # this router correctly ends the graph for that case.
    return "quiz_master" if state.get("awaiting_retry") else END
