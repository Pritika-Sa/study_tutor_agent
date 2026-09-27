"""
MCP protocol tests for Phase 4.

Runs the REAL MCP server as a subprocess over stdio and drives it through
the REAL MCP client (backend/mcp_client/client.py) -- deliberately not a
same-process function-call test, since the whole point of Phase 4 is the
protocol boundary. Each test connects its own client/subprocess (see
mcp_client's docstring on why a real app reuses one connection for its
whole lifetime -- these tests trade that speed for full isolation, since a
generate_quiz-heavy suite is not what's being measured here).

Isolation: DATABASE_URL and CHROMA_PERSIST_DIRECTORY point at a temp file
and temp directory for this whole module (env vars, so the subprocess sees
them too -- see mcp_client/client.py's docstring on environment forwarding).
Neither the real app.db nor the real data/chroma/ is touched.

No live GROQ_API_KEY exists in this environment. generate_quiz's LLM call
is stubbed via MCP_TEST_FAKE_LLM_QUESTIONS (see mcp_server/quiz_tools.py) --
this exercises the real MCP protocol, real RAG grounding, real validation,
real DB storage, and real answer-key hiding; it does not exercise the real
Groq API itself.
"""
import asyncio
import json
import os
from pathlib import Path

import pytest
from langchain_core.documents import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mcp_client.client import MCPClient, MCPToolError

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


@pytest.fixture(scope="module", autouse=True)
def isolated_mcp_environment(tmp_path_factory):
    """Isolated DB + Chroma dir for this whole module, seeded with one student and synthetic (non-NPTEL) DBMS content."""
    tmp_path = tmp_path_factory.mktemp("mcp_test")
    db_path = tmp_path / "mcp_test.db"
    chroma_path = tmp_path / "mcp_test_chroma"

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["CHROMA_PERSIST_DIRECTORY"] = str(chroma_path)
    os.environ["MCP_TEST_FAKE_LLM_QUESTIONS"] = json.dumps(FAKE_QUESTIONS)

    from config import settings
    settings.DATABASE_URL = os.environ["DATABASE_URL"]
    settings.CHROMA_PERSIST_DIRECTORY = str(chroma_path)

    # Create tables against a throwaway engine bound to the isolated DB file
    # -- avoids touching the already-imported database.database module's
    # cached engine (which was built from an earlier DATABASE_URL).
    from database.database import Base
    import database.models  # noqa: F401 -- registers all tables on Base.metadata

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    from auth.auth import hash_password
    from database.models import User

    db = Session()
    try:
        user = User(name="MCP Test Student", email="mcp.test@example.com", password_hash=hash_password("password123"))
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

    yield {"student_id": student_id, "db_path": db_path}

    vectorstore_module.get_vectorstore.cache_clear()


def _make_user(db_path: Path, email: str) -> str:
    """Creates an extra isolated test user, for tests that need their own clean progress history."""
    from database.database import Base
    from auth.auth import hash_password
    from database.models import User

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        user = User(name="Extra Test Student", email=email, password_hash=hash_password("password123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        return str(user.id)
    finally:
        db.close()
        engine.dispose()


def run(coro):
    """Runs one MCP round-trip in its own event loop -- see module docstring for why tests don't share a client."""
    return asyncio.run(coro)


async def _with_client(body):
    client = MCPClient()
    try:
        await client.connect()
        return await body(client)
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Server startup / tool discovery
# ---------------------------------------------------------------------------

def test_mcp_server_starts_and_lists_all_tools():
    async def body(client: MCPClient):
        return await client.list_tool_names()

    tool_names = set(run(_with_client(body)))

    required = {"generate_quiz", "save_progress", "get_weak_topics", "get_student_history", "get_topic_mastery"}
    assert required.issubset(tool_names)
    # Documented additions beyond the required 5 -- each exists so a specific
    # agent/route never has to import quiz_tools.py/progress_tools.py or the
    # ORM models directly (see their docstrings for which one and why).
    assert {"get_quiz_answer_key", "save_revision_plan", "get_latest_revision_plan"}.issubset(tool_names)


# ---------------------------------------------------------------------------
# generate_quiz: validation, grounding, answer-key hiding
# ---------------------------------------------------------------------------

def test_generate_quiz_rejects_invalid_track(isolated_mcp_environment):
    async def body(client: MCPClient):
        return await client.call_tool("generate_quiz", {
            "student_id": isolated_mcp_environment["student_id"],
            "track": "Medicine", "subject": "DBMS", "topic": "Normalization",
            "difficulty": "easy", "number_of_questions": 2,
        })

    with pytest.raises(MCPToolError):
        run(_with_client(body))


def test_generate_quiz_rejects_invalid_subject(isolated_mcp_environment):
    async def body(client: MCPClient):
        return await client.call_tool("generate_quiz", {
            "student_id": isolated_mcp_environment["student_id"],
            "track": "Placement", "subject": "Biology", "topic": "Normalization",
            "difficulty": "easy", "number_of_questions": 2,
        })

    with pytest.raises(MCPToolError):
        run(_with_client(body))


def test_generate_quiz_insufficient_rag_rejected(isolated_mcp_environment):
    """No content was ever ingested for Placement/SQL -- must refuse, not fabricate."""
    async def body(client: MCPClient):
        return await client.call_tool("generate_quiz", {
            "student_id": isolated_mcp_environment["student_id"],
            "track": "Placement", "subject": "SQL", "topic": "Window Functions",
            "difficulty": "easy", "number_of_questions": 2,
        })

    with pytest.raises(MCPToolError, match="Insufficient source material"):
        run(_with_client(body))


def test_generate_quiz_succeeds_and_hides_answer_key(isolated_mcp_environment):
    async def body(client: MCPClient):
        return await client.call_tool("generate_quiz", {
            "student_id": isolated_mcp_environment["student_id"],
            "track": "Placement", "subject": "DBMS", "topic": "Normalization",
            "difficulty": "easy", "number_of_questions": 2,
        })

    result = run(_with_client(body))

    assert "quiz_id" in result
    assert len(result["questions"]) == 2
    for question in result["questions"]:
        assert set(question.keys()) == {"question_id", "question", "options", "citation"}
        assert "correct_option" not in question
        assert question["citation"]["source"] == "OTHER"  # never fabricated as NPTEL


def test_get_quiz_answer_key_returns_correct_option_for_owner(isolated_mcp_environment):
    student_id = isolated_mcp_environment["student_id"]

    async def generate(client: MCPClient):
        return await client.call_tool("generate_quiz", {
            "student_id": student_id, "track": "Placement", "subject": "DBMS", "topic": "Normalization",
            "difficulty": "easy", "number_of_questions": 2,
        })

    async def fetch_key(client: MCPClient, quiz_id: str):
        return await client.call_tool("get_quiz_answer_key", {"quiz_id": quiz_id, "student_id": student_id})

    quiz = run(_with_client(generate))
    quiz_id = quiz["quiz_id"]

    answer_key = run(_with_client(lambda client: fetch_key(client, quiz_id)))

    assert answer_key["quiz_id"] == quiz_id
    correct_options = {q["correct_option"] for q in answer_key["questions"]}
    assert correct_options == {"Redundancy", "2NF"}


def test_get_quiz_answer_key_rejects_other_student(isolated_mcp_environment):
    owner_id = isolated_mcp_environment["student_id"]
    other_id = _make_user(isolated_mcp_environment["db_path"], "other.student@example.com")

    async def generate(client: MCPClient):
        return await client.call_tool("generate_quiz", {
            "student_id": owner_id, "track": "Placement", "subject": "DBMS", "topic": "Normalization",
            "difficulty": "easy", "number_of_questions": 2,
        })

    async def fetch_key_as_other(client: MCPClient, quiz_id: str):
        return await client.call_tool("get_quiz_answer_key", {"quiz_id": quiz_id, "student_id": other_id})

    quiz = run(_with_client(generate))
    quiz_id = quiz["quiz_id"]

    with pytest.raises(MCPToolError):
        run(_with_client(lambda client: fetch_key_as_other(client, quiz_id)))


# ---------------------------------------------------------------------------
# save_progress / get_weak_topics / get_student_history / get_topic_mastery
# ---------------------------------------------------------------------------

def test_save_progress_first_attempt_and_rolling_average(isolated_mcp_environment):
    student_id = _make_user(isolated_mcp_environment["db_path"], "progress.one@example.com")

    async def save(client: MCPClient, score, total):
        return await client.call_tool("save_progress", {
            "student_id": student_id, "track": "Placement", "subject": "DBMS", "topic": "Normalization",
            "score": score, "total_questions": total, "timestamp": "2026-09-27T00:00:00Z",
        })

    first = run(_with_client(lambda c: save(c, 2, 5)))   # 40%
    assert first["mastery"] == 40.0

    second = run(_with_client(lambda c: save(c, 4, 5)))  # 80% -> rolling avg of (40, 80) = 60
    assert second["mastery"] == 60.0


def test_get_weak_topics_returns_only_below_threshold(isolated_mcp_environment):
    student_id = _make_user(isolated_mcp_environment["db_path"], "weak.topics@example.com")

    async def save(client: MCPClient, subject, topic, score, total):
        return await client.call_tool("save_progress", {
            "student_id": student_id, "track": "Placement", "subject": subject, "topic": topic,
            "score": score, "total_questions": total, "timestamp": "2026-09-27T00:00:00Z",
        })

    run(_with_client(lambda c: save(c, "DBMS", "Normalization", 2, 5)))   # 40% -- weak
    run(_with_client(lambda c: save(c, "DBMS", "SQL Joins", 4, 5)))       # 80% -- not weak

    async def weak(client: MCPClient):
        return await client.call_tool("get_weak_topics", {"student_id": student_id, "track": "Placement"})

    result = run(_with_client(weak))
    topics = {t["topic"] for t in result["weak_topics"]}
    assert topics == {"Normalization"}
    assert result["weak_topics"][0]["mastery"] == 40.0


def test_get_student_history_sorted_newest_first(isolated_mcp_environment):
    student_id = _make_user(isolated_mcp_environment["db_path"], "history.student@example.com")

    async def save(client: MCPClient, topic, score):
        return await client.call_tool("save_progress", {
            "student_id": student_id, "track": "Placement", "subject": "DBMS", "topic": topic,
            "score": score, "total_questions": 5, "timestamp": "2026-09-27T00:00:00Z",
        })

    run(_with_client(lambda c: save(c, "Normalization", 2)))
    run(_with_client(lambda c: save(c, "SQL Joins", 4)))

    async def history(client: MCPClient):
        return await client.call_tool("get_student_history", {"student_id": student_id, "track": "Placement", "limit": 10})

    result = run(_with_client(history))
    topics_in_order = [a["topic"] for a in result["attempts"]]
    assert topics_in_order == ["SQL Joins", "Normalization"]  # most recent first


def test_get_topic_mastery_zero_when_no_record(isolated_mcp_environment):
    student_id = _make_user(isolated_mcp_environment["db_path"], "no.record@example.com")

    async def mastery(client: MCPClient):
        return await client.call_tool("get_topic_mastery", {
            "student_id": student_id, "track": "Placement", "subject": "DBMS", "topic": "Never Attempted",
        })

    result = run(_with_client(mastery))
    assert result == {"topic": "Never Attempted", "mastery": 0.0, "attempts": 0}


def test_get_topic_mastery_matches_after_save(isolated_mcp_environment):
    student_id = _make_user(isolated_mcp_environment["db_path"], "mastery.match@example.com")

    async def save(client: MCPClient):
        return await client.call_tool("save_progress", {
            "student_id": student_id, "track": "Placement", "subject": "DBMS", "topic": "Normalization",
            "score": 3, "total_questions": 5, "timestamp": "2026-09-27T00:00:00Z",
        })

    run(_with_client(save))

    async def mastery(client: MCPClient):
        return await client.call_tool("get_topic_mastery", {
            "student_id": student_id, "track": "Placement", "subject": "DBMS", "topic": "Normalization",
        })

    result = run(_with_client(mastery))
    assert result == {"topic": "Normalization", "mastery": 60.0, "attempts": 1}


# ---------------------------------------------------------------------------
# save_revision_plan / get_latest_revision_plan
# ---------------------------------------------------------------------------

def test_get_latest_revision_plan_none_when_never_generated(isolated_mcp_environment):
    student_id = _make_user(isolated_mcp_environment["db_path"], "no.plan@example.com")

    async def fetch(client: MCPClient):
        return await client.call_tool("get_latest_revision_plan", {"student_id": student_id, "track": "Placement"})

    result = run(_with_client(fetch))
    assert result == {"plan": None}


def test_save_and_get_latest_revision_plan_roundtrip(isolated_mcp_environment):
    student_id = _make_user(isolated_mcp_environment["db_path"], "plan.roundtrip@example.com")
    plan = {"items": [{"topic": "Normalization", "priority": "high"}]}

    async def save(client: MCPClient):
        return await client.call_tool("save_revision_plan", {"student_id": student_id, "track": "Placement", "plan": plan})

    save_result = run(_with_client(save))
    assert save_result["status"] == "ok"

    async def fetch(client: MCPClient):
        return await client.call_tool("get_latest_revision_plan", {"student_id": student_id, "track": "Placement"})

    fetched = run(_with_client(fetch))
    assert fetched["plan"] == plan
    assert fetched["track"] == "Placement"
