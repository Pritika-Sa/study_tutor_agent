"""
LangGraph workflow assembly (Phase 5).

Graph shape:
    START -> planner -> {explainer, quiz_master, evaluator, revision_planner, off_track_reply}
    quiz_master -> END                          (always waits for a submission)
    evaluator -> {explainer, revision_planner}  (adaptive routing -- graph/routing.py)
    explainer -> {quiz_master, END}             (retry-loop continuation vs. standalone explain)
    revision_planner -> END
    off_track_reply -> END

Checkpointing: LangGraph's AsyncSqliteSaver, pointed at the exact same
SQLite file as the rest of the app (settings.sqlite_file_path) -- required
because /quiz/start and /quiz/submit are two separate HTTP requests, and
resuming a thread_id is what lets the second request's ainvoke() continue
where the first left off (empirically verified: a partial input dict merges
onto the prior checkpoint's state rather than replacing it -- see the
Phase 4-7 report for how this was confirmed before relying on it).
"""
from contextlib import AsyncExitStack
from typing import Optional

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from agents.evaluator import evaluator_node
from agents.explainer import explainer_node
from agents.planner import planner_node
from agents.quiz_master import quiz_master_node
from agents.revision_planner import revision_planner_node
from config import settings
from graph.routing import route_after_evaluator, route_after_explainer, route_after_planner
from graph.state import AgentState


def _off_track_reply_node(state: AgentState) -> dict:
    return {"final_answer": state.get("final_answer") or "This request is not part of your selected track."}


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("explainer", explainer_node)
    graph.add_node("quiz_master", quiz_master_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("revision_planner", revision_planner_node)
    graph.add_node("off_track_reply", _off_track_reply_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_after_planner)
    graph.add_conditional_edges("evaluator", route_after_evaluator)
    graph.add_conditional_edges("explainer", route_after_explainer)
    graph.add_edge("quiz_master", END)
    graph.add_edge("revision_planner", END)
    graph.add_edge("off_track_reply", END)

    return graph


class GraphApp:
    """Owns the compiled graph + its checkpointer connection for the process's lifetime (see main.py's lifespan)."""

    def __init__(self) -> None:
        self._exit_stack: Optional[AsyncExitStack] = None
        self.compiled = None

    async def start(self) -> None:
        if self.compiled is not None:
            return
        exit_stack = AsyncExitStack()
        checkpointer = await exit_stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(str(settings.sqlite_file_path))
        )
        self._exit_stack = exit_stack
        self.compiled = build_graph().compile(checkpointer=checkpointer)

    async def stop(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self.compiled = None

    async def ainvoke(self, state_update: AgentState, thread_id: str) -> AgentState:
        if self.compiled is None:
            raise RuntimeError("GraphApp.start() must be called before ainvoke()")
        config = {"configurable": {"thread_id": thread_id}}
        return await self.compiled.ainvoke(state_update, config=config)


_graph_app: Optional[GraphApp] = None


def get_graph_app() -> GraphApp:
    """Process-wide singleton -- mirrors mcp_client.client.get_mcp_client()'s pattern."""
    global _graph_app
    if _graph_app is None:
        _graph_app = GraphApp()
    return _graph_app


async def reset_graph_app() -> None:
    """Closes and drops the singleton. Used by tests to get an isolated checkpointer per test module."""
    global _graph_app
    if _graph_app is not None:
        await _graph_app.stop()
    _graph_app = None
