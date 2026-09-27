"""
LangGraph orchestration tests for Phase 5/6.

Isolation: DATABASE_URL and CHROMA_PERSIST_DIRECTORY point at a temp file
and temp directory for this whole module (same pattern as test_mcp.py) --
neither the real app.db nor the real data/chroma/ is touched.

No live GROQ_API_KEY or TAVILY_API_KEY exists in this environment:
- Explainer's `_call_groq_for_explanation` is monkeypatched at module scope
  (a plain in-process function reassignment -- explainer/planner nodes never
  go through the MCP subprocess, so this is a normal monkeypatch, not the
  env-var seam quiz generation needs).
- Explainer's `_call_tavily_search` (imported into agents.explainer's own
  namespace) is likewise monkeypatched per-test to return either a
  deterministic fake result (with a genuinely fake, clearly-labelled URL,
  to verify URL preservation) or an empty list (to verify the iteration
  limit's honest "insufficient" behavior).
- generate_quiz's LLM call is stubbed via MCP_TEST_FAKE_LLM_QUESTIONS (see
  mcp_server/quiz_tools.py) -- same mechanism as test_mcp.py, since that
  call happens inside the MCP server subprocess, not this process.
"""
import asyncio
import json
import os
import uuid

import pytest
from langchain_core.documents import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import agents.explainer as explainer_module
from graph.state import new_state, resume_with_answers
from graph.workflow import GraphApp
from mcp_client.client import MCPClient

FAKE_QUESTIONS = [
    {
        "question": "What does normalization primarily reduce in a relational database?",
        "options": ["Redundancy", "Index size", "Network latency", "Page faults"],
        "correct_option": "Redundancy",
    },
    {
        "question": "Which normal form addresses partial functional dependency on a composite key?",
        "options": ["1NF", "2NF", "3NF", "BCNF"],
        "correct_option": "2NF",
    },
]
HIGH_SCORE_ANSWERS = {"q1": "A", "q2": "B"}  # both correct -> 100%
LOW_SCORE_ANSWERS = {"q1": "C", "q2": "D"}   # both wrong -> 0%


@pytest.fixture(scope="module", autouse=True)
def isolated_graph_environment(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("graph_test")
    db_path = tmp_path / "graph_test.db"
    chroma_path = tmp_path / "graph_test_chroma"

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["CHROMA_PERSIST_DIRECTORY"] = str(chroma_path)
    os.environ["MCP_TEST_FAKE_LLM_QUESTIONS"] = json.dumps(FAKE_QUESTIONS)

    from config import settings
    settings.DATABASE_URL = os.environ["DATABASE_URL"]
    settings.CHROMA_PERSIST_DIRECTORY = str(chroma_path)

    from database.database import Base
    import database.models  # noqa: F401

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    from auth.auth import hash_password
    from database.models import User

    db = Session()
    try:
        user = User(name="Graph Test Student", email="graph.test@example.com", password_hash=hash_password("password123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        student_id = str(user.id)
    finally:
        db.close()
        engine.dispose()

    from rag import vectorstore as vectorstore_module
    vectorstore_module.get_vectorstore.cache_clear()

    doc = Document(
        page_content=(
            "Normalization is the process of organizing columns and tables in a relational "
            "database to reduce data redundancy. Second normal form (2NF) removes partial "
            "functional dependency of non-key attributes on a composite primary key."
        ),
        metadata={
            "track": "Placement", "subject": "DBMS", "source": "OTHER",
            "document_name": "sample_dbms_notes.pdf", "page": 1,
            "chapter": "Normalization", "chunk_index": 0,
        },
    )
    from rag.vectorstore import add_chunks
    add_chunks("Placement", [doc])

    yield {"student_id": student_id}

    vectorstore_module.get_vectorstore.cache_clear()


def run(coro):
    return asyncio.run(coro)


def _fake_groq_explanation(*, query, context_chunks, web_snippets, subject, topic, difficulty):
    return "GROUNDED ANSWER: " + " ".join(context_chunks + web_snippets)[:500]


@pytest.fixture(autouse=True)
def stub_groq_explanation(monkeypatch):
    monkeypatch.setattr(explainer_module, "_call_groq_for_explanation", _fake_groq_explanation)


EMPTY_SUPPLEMENTARY_RESOURCES = {"videos": [], "articles": [], "real_world_examples": []}


@pytest.fixture(autouse=True)
def stub_supplementary_resources(monkeypatch):
    """
    Default stub so every test in this module -- including ones that never
    mention supplementary resources -- stays offline: without this,
    explainer_node's new get_supplementary_resources call would hit the
    real Tavily API whenever a real TAVILY_API_KEY happens to be configured
    in backend/.env (Settings() loads it regardless of this module's own
    DATABASE_URL/CHROMA_PERSIST_DIRECTORY isolation). Individual tests
    override this via monkeypatch to exercise real categorization/shape.
    """
    monkeypatch.setattr(explainer_module, "get_supplementary_resources", lambda **kwargs: dict(EMPTY_SUPPLEMENTARY_RESOURCES))


# ---------------------------------------------------------------------------
# Planner routing / guardrails (no MCP subprocess needed for these)
# ---------------------------------------------------------------------------

def test_planner_off_track_rejects_mismatched_subject(isolated_graph_environment):
    async def body():
        graph_app = GraphApp()
        await graph_app.start()
        try:
            state = new_state(
                student_id=isolated_graph_environment["student_id"],
                thread_id=f"test-offtrack-{uuid.uuid4().hex}",
                user_query="Explain photosynthesis",
                learning_track="Placement",
                subject="Biology",  # not a Placement subject
                intent="explain",
            )
            return await graph_app.ainvoke(state, thread_id=state["thread_id"])
        finally:
            await graph_app.stop()

    result = run(body())
    assert result["intent"] == "off_track"
    assert "not part of your selected" in result["final_answer"]


def test_explain_intent_uses_rag_when_sufficient(isolated_graph_environment):
    async def body():
        graph_app = GraphApp()
        await graph_app.start()
        try:
            state = new_state(
                student_id=isolated_graph_environment["student_id"],
                thread_id=f"test-explain-{uuid.uuid4().hex}",
                user_query="What is database normalization?",
                learning_track="Placement",
                subject="DBMS",
                topic="Normalization",
                intent="explain",
            )
            return await graph_app.ainvoke(state, thread_id=state["thread_id"])
        finally:
            await graph_app.stop()

    result = run(body())
    assert result["source_type"] == "KB"
    assert result["react_iteration_count"] == 1  # sufficient on the first RAG lookup -- no extra iterations spent
    assert result["citations"][0]["source"] == "OTHER"  # never fabricated as NPTEL
    assert result["final_answer"].startswith("GROUNDED ANSWER:")
    assert result["supplementary_resources"] == EMPTY_SUPPLEMENTARY_RESOURCES  # default stub -- see fixture above


def test_explain_intent_includes_supplementary_resources_when_rag_sufficient(isolated_graph_environment, monkeypatch):
    """
    Wiring test: when get_supplementary_resources finds real, categorized
    results, they flow through explainer_node -> AgentState -> the graph's
    final result unchanged (no reclassification, no fabricated fields).
    tools/tavily_tool.py's own unit tests (test_supplementary_resources.py)
    cover the categorization/dedup/limit logic itself in isolation.
    """
    fake_resources = {
        "videos": [{"title": "Normalization Explained", "url": "https://youtube.com/watch?v=abc123",
                    "description": "A walkthrough of 1NF/2NF/3NF.", "resource_type": "VIDEO", "source": "youtube.com"}],
        "articles": [{"title": "Database Normalization", "url": "https://example.edu/normalization",
                      "description": "University reference page.", "resource_type": "ARTICLE", "source": "example.edu"}],
        "real_world_examples": [],
    }
    monkeypatch.setattr(explainer_module, "get_supplementary_resources", lambda **kwargs: fake_resources)

    async def body():
        graph_app = GraphApp()
        await graph_app.start()
        try:
            state = new_state(
                student_id=isolated_graph_environment["student_id"],
                thread_id=f"test-supplementary-{uuid.uuid4().hex}",
                user_query="What is database normalization?",
                learning_track="Placement",
                subject="DBMS",
                topic="Normalization",
                intent="explain",
            )
            return await graph_app.ainvoke(state, thread_id=state["thread_id"])
        finally:
            await graph_app.stop()

    result = run(body())
    assert result["source_type"] == "KB"
    assert result["supplementary_resources"] == fake_resources
    # The primary RAG-grounded answer is unaffected by supplementary resources.
    assert result["final_answer"].startswith("GROUNDED ANSWER:")


def test_explain_intent_skips_supplementary_resources_when_nothing_answerable(isolated_graph_environment, monkeypatch):
    """No RAG match and no Tavily fallback result -- nothing to supplement, so get_supplementary_resources must not even be called."""
    called = []
    monkeypatch.setattr(explainer_module, "_call_tavily_search", lambda **kwargs: [])
    monkeypatch.setattr(explainer_module, "get_supplementary_resources", lambda **kwargs: called.append(kwargs) or dict(EMPTY_SUPPLEMENTARY_RESOURCES))

    async def body():
        graph_app = GraphApp()
        await graph_app.start()
        try:
            state = new_state(
                student_id=isolated_graph_environment["student_id"],
                thread_id=f"test-no-supplementary-{uuid.uuid4().hex}",
                user_query="Explain a completely unseeded aptitude concept",
                learning_track="Placement",
                subject="DBMS",
                topic="Nonexistent Topic",
                intent="explain",
            )
            return await graph_app.ainvoke(state, thread_id=state["thread_id"])
        finally:
            await graph_app.stop()

    result = run(body())
    assert result["source_type"] == "NONE"
    assert result["supplementary_resources"] == EMPTY_SUPPLEMENTARY_RESOURCES
    assert called == []  # never even attempted -- not just empty results


# ---------------------------------------------------------------------------
# ReAct: ru insufficient RAG -> Tavily fallback / iteration limit
# ---------------------------------------------------------------------------

def test_react_falls_back_to_tavily_and_preserves_real_url(isolated_graph_environment, monkeypatch):
    fake_web_result = [{"title": "SQL Window Functions Guide", "url": "https://example-test-source.invalid/window-functions", "content": "Window functions compute a value across a set of rows."}]
    monkeypatch.setattr(explainer_module, "_call_tavily_search", lambda **kwargs: fake_web_result)

    async def body():
        graph_app = GraphApp()
        await graph_app.start()
        try:
            state = new_state(
                student_id=isolated_graph_environment["student_id"],
                thread_id=f"test-tavily-{uuid.uuid4().hex}",
                user_query="Explain SQL window functions",
                learning_track="Placement",
                subject="DBMS",
                topic="Window Functions",  # nothing seeded for this topic/subject-wide search either
                intent="explain",
            )
            return await graph_app.ainvoke(state, thread_id=state["thread_id"])
        finally:
            await graph_app.stop()

    result = run(body())
    assert result["source_type"] in {"WEB", "KB+WEB"}
    assert result["web_results"][0]["url"] == "https://example-test-source.invalid/window-functions"  # preserved exactly
    assert result["react_iteration_count"] <= 3  # REACT_MAX_ITERATIONS default


def test_react_iteration_limit_enforced_and_no_fabrication(isolated_graph_environment, monkeypatch):
    monkeypatch.setattr(explainer_module, "_call_tavily_search", lambda **kwargs: [])  # simulate no web results available

    async def body():
        graph_app = GraphApp()
        await graph_app.start()
        try:
            state = new_state(
                student_id=isolated_graph_environment["student_id"],
                thread_id=f"test-insufficient-{uuid.uuid4().hex}",
                user_query="Explain a completely unseeded aptitude concept",
                learning_track="Placement",
                subject="DBMS",
                topic="Nonexistent Topic",
                intent="explain",
            )
            return await graph_app.ainvoke(state, thread_id=state["thread_id"])
        finally:
            await graph_app.stop()

    result = run(body())
    from config import settings
    assert result["react_iteration_count"] <= settings.REACT_MAX_ITERATIONS
    assert result["source_type"] == "NONE"
    assert "limited" in result["final_answer"].lower()
    assert not result["citations"]  # nothing fabricated


# ---------------------------------------------------------------------------
# Full adaptive loop: quiz -> low score -> retry -> high score -> revision plan
# ---------------------------------------------------------------------------

def test_full_adaptive_loop_and_retry_limit(isolated_graph_environment):
    student_id = isolated_graph_environment["student_id"]

    async def body():
        graph_app = GraphApp()
        mcp_client = MCPClient()
        await graph_app.start()
        await mcp_client.connect()

        # Monkeypatch the module-level MCP client singleton so agent nodes
        # (which call mcp_client.client.get_mcp_client()) reuse this same
        # already-connected client instead of spawning a second subprocess.
        import mcp_client.client as client_module
        client_module._client = mcp_client

        try:
            thread_id = f"test-adaptive-{uuid.uuid4().hex}"

            # --- Round 1: start quiz ---
            state = new_state(
                student_id=student_id, thread_id=thread_id, user_query="",
                learning_track="Placement", subject="DBMS", topic="Normalization",
                intent="quiz", difficulty="easy", number_of_questions=2,
            )
            r1 = await graph_app.ainvoke(state, thread_id=thread_id)
            quiz_id_1 = r1["quiz_id"]
            assert quiz_id_1

            # --- Round 1 submit: LOW score -> expect a retry ---
            # Note: the retry chain (evaluator -> explainer -> quiz_master) all
            # runs within this ONE ainvoke() call, so by the time it returns,
            # quiz_master has already cleared score/percentage for the FRESH
            # quiz it just generated (see agents/quiz_master.py) -- the grade
            # for THIS submission is still visible in `feedback`.
            r2 = await graph_app.ainvoke(resume_with_answers(LOW_SCORE_ANSWERS), thread_id=thread_id)
            assert "0/2 (0.0%)" in r2["feedback"]
            assert r2["awaiting_retry"] is True
            assert r2["adaptive_loop_count"] == 1
            quiz_id_2 = r2["quiz_id"]
            assert quiz_id_2 and quiz_id_2 != quiz_id_1  # a fresh quiz was actually regenerated

            # --- Round 2 submit: LOW score again -> second retry (still under ADAPTIVE_MAX_RETRIES=2) ---
            r3 = await graph_app.ainvoke(resume_with_answers(LOW_SCORE_ANSWERS), thread_id=thread_id)
            assert r3["awaiting_retry"] is True
            assert r3["adaptive_loop_count"] == 2
            quiz_id_3 = r3["quiz_id"]
            assert quiz_id_3 and quiz_id_3 != quiz_id_2

            # --- Round 3 submit: LOW score a third time -> retries exhausted, forced to revision plan ---
            r4 = await graph_app.ainvoke(resume_with_answers(LOW_SCORE_ANSWERS), thread_id=thread_id)
            assert r4["awaiting_retry"] is False  # forced stop -- guardrail against an uncontrolled loop
            assert r4["adaptive_loop_count"] == 2  # never exceeds ADAPTIVE_MAX_RETRIES
            assert r4["revision_plan"] is not None
            plan = json.loads(r4["revision_plan"])
            assert plan["track"] == "Placement"
            assert any(item.get("topic") == "Normalization" for item in plan["items"])

            # --- Separately: intent="revision" invoked directly on a fresh thread ---
            revision_thread = f"test-direct-revision-{uuid.uuid4().hex}"
            revision_state = new_state(
                student_id=student_id, thread_id=revision_thread, user_query="",
                learning_track="Placement", subject="DBMS", intent="revision",
            )
            r5 = await graph_app.ainvoke(revision_state, thread_id=revision_thread)
            assert r5["revision_plan"] is not None
            assert r5["final_answer"] == "Revision plan generated."

        finally:
            client_module._client = None
            await mcp_client.close()
            await graph_app.stop()

    run(body())
