"""
API integration tests for Phase 7 -- also where the required end-to-end
scenario lives: register -> login -> ask -> quiz start -> quiz submit ->
weak topics -> revision plan.

Isolation: DATABASE_URL and CHROMA_PERSIST_DIRECTORY point at a temp file
and temp directory for this whole module (same pattern as test_mcp.py /
test_graph.py) -- the real app.db and data/chroma/ are never touched.
Synthetic (source=OTHER, never NPTEL) DBMS content is seeded directly.
generate_quiz's LLM call is stubbed via MCP_TEST_FAKE_LLM_QUESTIONS (see
mcp_server/quiz_tools.py) and the Explainer's Groq call is monkeypatched
per-test -- no live GROQ_API_KEY exists in this environment.

`with TestClient(app) as client:` runs the real FastAPI lifespan, which
means the real MCP server subprocess and the real LangGraph checkpointer
both start up for this module, exactly as they would in production.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

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


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("api_test")
    db_path = tmp_path / "api_test.db"
    chroma_path = tmp_path / "api_test_chroma"

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["CHROMA_PERSIST_DIRECTORY"] = str(chroma_path)
    os.environ["MCP_TEST_FAKE_LLM_QUESTIONS"] = json.dumps(FAKE_QUESTIONS)

    from config import settings
    settings.DATABASE_URL = os.environ["DATABASE_URL"]
    settings.CHROMA_PERSIST_DIRECTORY = str(chroma_path)

    # database.database's `engine` is a module-level singleton bound at
    # first import -- if an earlier test module already imported it (against
    # a different isolated DATABASE_URL), main.py's lifespan create_tables()
    # would create tables in THAT stale engine's file, not this module's
    # isolated db_path, leaving the MCP subprocess's freshly-built engine
    # (which correctly reads DATABASE_URL from the environment at spawn
    # time) pointing at a file with no tables. Create tables explicitly
    # against a throwaway engine bound to this module's own path instead --
    # the same pattern test_mcp.py/test_graph.py already use, for the same
    # reason. (Caught by running the full suite together, not standalone --
    # see the Phase 4-7 report.)
    from sqlalchemy import create_engine as _create_engine
    from database.database import Base
    import database.models  # noqa: F401

    _setup_engine = _create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=_setup_engine)
    _setup_engine.dispose()

    from rag import vectorstore as vectorstore_module
    vectorstore_module.get_vectorstore.cache_clear()

    from rag.vectorstore import add_chunks
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
    add_chunks("Placement", [doc])

    # Default-stub supplementary-resource search for this whole module:
    # without this, explainer_node's get_supplementary_resources call would
    # hit the real Tavily API on every /tutor/ask test whenever a real
    # TAVILY_API_KEY happens to be configured in backend/.env (Settings()
    # loads it regardless of this fixture's own DATABASE_URL/CHROMA
    # isolation). Individual tests can still override this via the
    # function-scoped `monkeypatch` fixture (it saves/restores whatever
    # value is current -- this stub -- around that one test).
    import agents.explainer as explainer_module
    original_get_supplementary_resources = explainer_module.get_supplementary_resources
    explainer_module.get_supplementary_resources = lambda **kwargs: {
        "videos": [], "articles": [], "real_world_examples": [],
    }

    from main import app  # imported here, after settings are pointed at the isolated paths

    with TestClient(app) as test_client:
        yield test_client

    explainer_module.get_supplementary_resources = original_get_supplementary_resources
    vectorstore_module.get_vectorstore.cache_clear()


def _register_and_login(client: TestClient, email: str) -> str:
    client.post("/auth/register", json={"name": "Test Student", "email": email, "password": "password123"})
    resp = client.post("/auth/login", json={"email": email, "password": "password123"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# /tracks
# ---------------------------------------------------------------------------

def test_tracks_requires_auth(client):
    assert client.get("/tracks").status_code == 401


def test_tracks_returns_expected_structure(client):
    token = _register_and_login(client, "tracks.user@example.com")
    body = client.get("/tracks", headers=_auth(token)).json()
    assert set(body["NEET"]) == {"Physics", "Chemistry", "Biology"}
    assert set(body["Placement"]) == {"Java", "SQL", "Aptitude", "DBMS", "DSA"}


# ---------------------------------------------------------------------------
# /tutor/ask
# ---------------------------------------------------------------------------

def test_tutor_ask_requires_auth(client):
    resp = client.post("/tutor/ask", json={"track": "Placement", "subject": "DBMS", "query": "What is normalization?"})
    assert resp.status_code == 401


def test_tutor_ask_returns_grounded_answer_with_citation(client, monkeypatch):
    import agents.explainer as explainer_module
    monkeypatch.setattr(
        explainer_module, "_call_groq_for_explanation",
        lambda **kwargs: "Normalization reduces redundancy. " + " ".join(kwargs["context_chunks"])[:200],
    )

    token = _register_and_login(client, "ask.user@example.com")
    resp = client.post(
        "/tutor/ask",
        json={"track": "Placement", "subject": "DBMS", "query": "What is database normalization?"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_type"] == "KB"
    assert body["citations"][0]["source"] == "OTHER"
    assert "Normalization" in body["answer"]


def test_tutor_ask_includes_empty_supplementary_resources_by_default(client, monkeypatch):
    """
    The module-wide stub (see the `client` fixture) returns no resources --
    this confirms /tutor/ask's response always includes the
    supplementary_resources key with the empty-lists shape (never omitted,
    never null) rather than only when resources happen to exist, and that
    the existing response fields are completely unaffected.
    """
    import agents.explainer as explainer_module
    monkeypatch.setattr(
        explainer_module, "_call_groq_for_explanation",
        lambda **kwargs: "Normalization reduces redundancy.",
    )

    token = _register_and_login(client, "ask.nosupplementary@example.com")
    resp = client.post(
        "/tutor/ask",
        json={"track": "Placement", "subject": "DBMS", "query": "What is database normalization?"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    # Existing fields: unchanged.
    assert body["source_type"] == "KB"
    assert body["citations"][0]["source"] == "OTHER"
    # New field: always present, empty here since Tavily is stubbed to find nothing.
    assert body["supplementary_resources"] == {"videos": [], "articles": [], "real_world_examples": []}


def test_tutor_ask_includes_real_supplementary_resources_when_available(client, monkeypatch):
    """
    Resources contain real (mocked) Tavily URLs, correctly categorized --
    nothing fabricated, nothing dropped. Mocks _call_tavily_search itself
    (not get_supplementary_resources) so the actual categorization/dedup/
    limit logic in tools/tavily_tool.py runs for real against realistic
    Tavily-shaped payloads (per-category results, since get_supplementary_resources
    issues one targeted query per category and _call_tavily_search doesn't
    see which query produced which call here -- so the same three mocked
    results are returned for every query, then filtered by URL shape exactly
    as get_supplementary_resources would filter real mixed results).
    """
    import agents.explainer as explainer_module
    import tools.tavily_tool as tavily_tool_module

    monkeypatch.setattr(
        explainer_module, "_call_groq_for_explanation",
        lambda **kwargs: "Normalization reduces redundancy.",
    )
    monkeypatch.setattr(explainer_module, "get_supplementary_resources", tavily_tool_module.get_supplementary_resources)
    monkeypatch.setattr(tavily_tool_module, "_call_tavily_search", lambda **kwargs: [
        {"title": "SQL Normalization Tutorial", "url": "https://www.youtube.com/watch?v=normalization1",
         "content": "A walkthrough of normal forms.", "score": 0.95},
        {"title": "Understanding Normalization", "url": "https://example.edu/normalization",
         "content": "University reference on normal forms.", "score": 0.9},
        {"title": "", "url": "not-a-valid-url", "content": "garbage"},  # must be dropped, never fabricated
    ])

    token = _register_and_login(client, "ask.withsupplementary@example.com")
    resp = client.post(
        "/tutor/ask",
        json={"track": "Placement", "subject": "DBMS", "query": "What is database normalization?"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    resources = resp.json()["supplementary_resources"]

    assert len(resources["videos"]) == 1
    assert resources["videos"][0]["url"] == "https://www.youtube.com/watch?v=normalization1"
    assert resources["videos"][0]["resource_type"] == "VIDEO"
    assert resources["videos"][0]["source"] == "youtube.com"

    assert len(resources["articles"]) == 1
    assert resources["articles"][0]["url"] == "https://example.edu/normalization"
    assert resources["articles"][0]["resource_type"] == "ARTICLE"

    # The malformed entry never became a resource anywhere.
    all_urls = [r["url"] for cat in resources.values() for r in cat]
    assert "not-a-valid-url" not in all_urls


def test_tutor_ask_rejects_off_track_subject(client):
    token = _register_and_login(client, "offtrack.user@example.com")
    resp = client.post(
        "/tutor/ask",
        json={"track": "Placement", "subject": "Biology", "query": "Explain photosynthesis"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /quiz/start, /quiz/submit
# ---------------------------------------------------------------------------

def test_quiz_start_never_exposes_answer_key(client):
    token = _register_and_login(client, "quiz.user@example.com")
    resp = client.post(
        "/quiz/start",
        json={"track": "Placement", "subject": "DBMS", "topic": "Normalization", "difficulty": "easy", "number_of_questions": 2},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "quiz_id" in body
    for question in body["questions"]:
        assert "correct_option" not in question
        assert "answer_key" not in question
        assert "solution" not in question


def test_quiz_submit_ignores_client_supplied_score(client):
    token = _register_and_login(client, "submit.user@example.com")
    start = client.post(
        "/quiz/start",
        json={"track": "Placement", "subject": "DBMS", "topic": "Normalization", "difficulty": "easy", "number_of_questions": 2},
        headers=_auth(token),
    )
    quiz_id = start.json()["quiz_id"]

    # Both answers wrong, but the payload ALSO tries to smuggle in a fake
    # score -- the server must ignore it and grade for real.
    resp = client.post(
        "/quiz/submit",
        json={"quiz_id": quiz_id, "answers": {"q1": "C", "q2": "D"}, "score": 100, "percentage": 100},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["percentage"] == 0.0
    assert body["score"] == 0


def test_quiz_submit_rejects_unknown_quiz_id(client):
    token = _register_and_login(client, "badquiz.user@example.com")
    resp = client.post("/quiz/submit", json={"quiz_id": "does-not-exist", "answers": {}}, headers=_auth(token))
    assert resp.status_code == 404


def test_user_cannot_submit_another_users_quiz(client):
    token_a = _register_and_login(client, "isolation.a@example.com")
    token_b = _register_and_login(client, "isolation.b@example.com")

    start = client.post(
        "/quiz/start",
        json={"track": "Placement", "subject": "DBMS", "topic": "Normalization", "difficulty": "easy", "number_of_questions": 2},
        headers=_auth(token_a),
    )
    quiz_id = start.json()["quiz_id"]

    resp = client.post("/quiz/submit", json={"quiz_id": quiz_id, "answers": {"q1": "A"}}, headers=_auth(token_b))
    assert resp.status_code == 404  # get_quiz_answer_key rejects the mismatched owner


# ---------------------------------------------------------------------------
# End-to-end: register -> login -> ask -> quiz start -> submit -> weak topics -> revision plan
# ---------------------------------------------------------------------------

def test_full_end_to_end_scenario(client, monkeypatch):
    import agents.explainer as explainer_module
    monkeypatch.setattr(
        explainer_module, "_call_groq_for_explanation",
        lambda **kwargs: "Grounded explanation: " + " ".join(kwargs["context_chunks"])[:200],
    )

    email = "e2e.student@example.com"
    reg = client.post("/auth/register", json={"name": "E2E Student", "email": email, "password": "password123"})
    assert reg.status_code == 201

    login = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200
    headers = _auth(login.json()["access_token"])

    ask_resp = client.post(
        "/tutor/ask", json={"track": "Placement", "subject": "DBMS", "query": "What is normalization?"}, headers=headers
    )
    assert ask_resp.status_code == 200
    assert ask_resp.json()["source_type"] == "KB"

    start_resp = client.post(
        "/quiz/start",
        json={"track": "Placement", "subject": "DBMS", "topic": "Normalization", "difficulty": "easy", "number_of_questions": 2},
        headers=headers,
    )
    assert start_resp.status_code == 200
    quiz_id = start_resp.json()["quiz_id"]

    submit_resp = client.post(
        "/quiz/submit",
        json={"quiz_id": quiz_id, "answers": {"q1": "C", "q2": "D"}},  # both wrong -> 0%, triggers an adaptive retry
        headers=headers,
    )
    assert submit_resp.status_code == 200
    submit_body = submit_resp.json()
    assert submit_body["percentage"] == 0.0
    assert submit_body["next_action"] == "retry_quiz"

    weak_resp = client.get("/weak-topics?track=Placement", headers=headers)
    assert weak_resp.status_code == 200
    assert any(t["topic"] == "Normalization" for t in weak_resp.json()["weak_topics"])

    progress_resp = client.get("/progress?track=Placement", headers=headers)
    assert progress_resp.status_code == 200
    assert "overall_percentage" in progress_resp.json()

    history_resp = client.get("/history?track=Placement", headers=headers)
    assert history_resp.status_code == 200
    assert len(history_resp.json()["attempts"]) >= 1

    revision_resp = client.get("/revision-plan?track=Placement", headers=headers)
    assert revision_resp.status_code == 200
    assert revision_resp.json()["plan"] is not None


# ---------------------------------------------------------------------------
# Revision plan freshness (bug: GET /revision-plan kept serving the first
# plan ever saved for a track forever, even after topic_progress moved on --
# see routes_progress.py's _weak_topics_snapshot/_plan_snapshot comparison).
# ---------------------------------------------------------------------------

def test_revision_plan_refreshes_when_new_weak_topics_appear(client, monkeypatch):
    """
    A quiz that scores low but still has retries remaining routes to
    explainer/quiz_master, NOT revision_planner (graph/routing.py's
    route_after_evaluator) -- so a student can pick up a brand-new weak
    topic (or a mastery change on an existing one) without the adaptive
    loop ever re-invoking the Revision Planner. This reproduces exactly
    that and asserts GET /revision-plan reflects the new weak topic rather
    than replaying whatever was saved after the first one.

    The second weak topic is recorded via a direct `save_progress` MCP call
    (a fresh, independent MCPClient -- same isolation pattern test_mcp.py
    uses) instead of a second full RAG-grounded quiz: save_progress is
    exactly the tool the real Evaluator calls after grading (see
    agents/evaluator.py), so this exercises the real production write path
    for topic_progress without a second real quiz-generation round trip,
    which is irrelevant to the staleness bug under test here.
    """
    import agents.explainer as explainer_module
    monkeypatch.setattr(explainer_module, "_call_groq_for_explanation", lambda **kwargs: "stub explanation")

    email = "revision.staleness@example.com"
    token = _register_and_login(client, email)
    headers = _auth(token)
    student_id = str(client.get("/auth/me", headers=headers).json()["id"])

    start = client.post(
        "/quiz/start",
        json={"track": "Placement", "subject": "DBMS", "topic": "Normalization", "difficulty": "easy", "number_of_questions": 2},
        headers=headers,
    )
    assert start.status_code == 200, start.text
    submit = client.post(
        "/quiz/submit",
        json={"quiz_id": start.json()["quiz_id"], "answers": {"q1": "C", "q2": "D"}},  # both wrong -> 0%
        headers=headers,
    )
    assert submit.status_code == 200, submit.text
    # Confirms the precondition this test depends on: retries remain, so
    # this quiz alone never reaches revision_planner_node.
    assert submit.json()["next_action"] == "retry_quiz"

    first = client.get("/revision-plan?track=Placement", headers=headers)
    assert first.status_code == 200
    first_plan = first.json()["plan"]
    assert {i["topic"] for i in first_plan["items"] if "topic" in i} == {"Normalization"}

    # Calling GET /revision-plan again with nothing changed must return the
    # SAME saved plan (not silently regenerate/duplicate on every request).
    unchanged = client.get("/revision-plan?track=Placement", headers=headers)
    assert unchanged.json()["plan"]["generated_at"] == first_plan["generated_at"]

    import asyncio
    from mcp_client.client import MCPClient

    async def _record_second_weak_topic():
        second_client = MCPClient()
        try:
            await second_client.connect()
            await second_client.call_tool("save_progress", {
                "student_id": student_id, "track": "Placement", "subject": "DBMS", "topic": "Indexing",
                "score": 1, "total_questions": 5,  # 20% -- below the 60% test threshold
            })
        finally:
            await second_client.close()

    asyncio.run(_record_second_weak_topic())

    second = client.get("/revision-plan?track=Placement", headers=headers)
    assert second.status_code == 200
    second_plan = second.json()["plan"]
    assert {i["topic"] for i in second_plan["items"] if "topic" in i} == {"Normalization", "Indexing"}
    # A genuinely new plan was generated (not the first one replayed) --
    # the old one still exists in revision_plans history (append-only,
    # see database/models.py: RevisionPlan has no update/delete path).
    assert second_plan["generated_at"] != first_plan["generated_at"]
