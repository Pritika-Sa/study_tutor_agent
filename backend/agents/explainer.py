"""
Explainer Agent -- also this project's ReAct agent (Phase 6).

ReAct loop, bounded by REACT_MAX_ITERATIONS (config), never uncontrolled:

    Reason -> RAG retrieve (topic-filtered)         [iteration 1]
    Observe -> sufficient? -> yes: compose answer
                            -> no:  Act -> RAG retrieve (subject-wide)   [iteration 2]
                                    Observe -> sufficient? -> yes: compose answer
                                                            -> no:  Act -> Tavily web search   [iteration 3]
                                                                    Observe -> compose best-available answer

`react_iteration_count` counts these Reason/Act cycles and is entirely
separate from `adaptive_loop_count` (the quiz retry counter in
graph/routing.py) -- one bounds this node's own tool-calling loop, the
other bounds the graph-level quiz/re-quiz loop. They are never conflated.

Uses rag/retriever.py as the only retrieval path (never queries ChromaDB
directly), and never fabricates a citation, a URL, or an answer when
sources are insufficient.
"""
import asyncio
import logging
from typing import Optional

from config import settings
from graph.state import AgentState
from rag.retriever import RetrievalResult, retrieve
from tools.tavily_tool import _call_tavily_search, get_supplementary_resources

logger = logging.getLogger(__name__)


def _call_groq_for_explanation(
    *,
    query: str,
    context_chunks: list[str],
    web_snippets: list[str],
    subject: str,
    topic: Optional[str],
    difficulty: Optional[str],
) -> str:
    """
    Real Groq call, isolated so tests can monkeypatch it. This environment
    has no live GROQ_API_KEY configured, so this exact function has not been
    exercised against the real Groq API -- see README "Known Limitations".
    """
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured -- cannot compose an explanation")

    from groq import Groq  # imported lazily: a missing/unused key never breaks module import

    client = Groq(api_key=settings.GROQ_API_KEY)
    sources_block = "\n\n".join(context_chunks + web_snippets)
    topic_part = f" ({topic})" if topic else ""
    prompt = (
        f"You are tutoring a student on {subject}{topic_part} at a {difficulty or 'medium'} level.\n"
        "Answer the student's question strictly using the SOURCE MATERIAL below -- do not use outside "
        "knowledge, and do not state anything the sources do not support. Explain clearly and include a "
        "short example only if the sources support one.\n\n"
        f"QUESTION: {query}\n\nSOURCE MATERIAL:\n{sources_block}"
    )
    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    return response.choices[0].message.content


async def explainer_node(state: AgentState) -> dict:
    track = state["learning_track"]
    subject = state["subject"]
    topic = state.get("topic")
    query = state["user_query"]
    difficulty = state.get("difficulty")

    iteration = 0

    # Reason + Act #1
    result: RetrievalResult = retrieve(query=query, track=track, subject=subject, topic=topic)
    iteration += 1

    # Act #2: widen to the whole subject if a topic filter was too narrow
    if not result.sufficient and topic and iteration < settings.REACT_MAX_ITERATIONS:
        result = retrieve(query=query, track=track, subject=subject, topic=None)
        iteration += 1

    context_chunks = [doc.content for doc in result.documents] if result.sufficient else []
    citations = [c.model_dump() for c in result.citations] if result.sufficient else []
    web_results: list[dict] = []
    source_type = "KB" if result.sufficient else "NONE"

    # Act #3: Tavily, only if still insufficient and the iteration budget allows it
    if not result.sufficient and iteration < settings.REACT_MAX_ITERATIONS:
        web_results = await asyncio.to_thread(_call_tavily_search, query=query, max_results=3)
        iteration += 1
        if web_results:
            source_type = "KB+WEB" if context_chunks else "WEB"

    web_snippets = [f"{w['title']}: {w['content']} (source: {w['url']})" for w in web_results]

    if not context_chunks and not web_snippets:
        final_answer = (
            "Available source coverage is limited for this question -- neither the knowledge base nor a "
            "supplementary web search returned enough grounded material to answer confidently. Please try "
            "rephrasing the question, or narrowing the topic."
        )
    else:
        try:
            final_answer = _call_groq_for_explanation(
                query=query, context_chunks=context_chunks, web_snippets=web_snippets,
                subject=subject, topic=topic, difficulty=difficulty,
            )
        except RuntimeError as exc:
            # No LLM configured -- return the grounded material itself, never fabricated prose.
            final_answer = (
                f"LLM composition is unavailable ({exc}). Grounded source material found:\n\n"
                + "\n\n".join(context_chunks + web_snippets)
            )

    web_citations = [{"title": w["title"], "url": w["url"]} for w in web_results]

    # Supplementary learning resources (videos/articles/real-world examples)
    # -- a separate, bounded concern from the ReAct ground-truth search
    # above, never counted against react_iteration_count/REACT_MAX_ITERATIONS
    # (it is not part of that Reason/Act loop) and never looped or recursed.
    # Skipped entirely when there is no real answer to supplement (the
    # "insufficient coverage" bail-out case) -- no point spending Tavily
    # calls on a question nothing could answer.
    if context_chunks or web_snippets:
        supplementary_resources = await asyncio.to_thread(
            get_supplementary_resources, track=track, subject=subject, topic=topic, query=query,
        )
    else:
        supplementary_resources = {"videos": [], "articles": [], "real_world_examples": []}

    return {
        "retrieved_context": context_chunks,
        "citations": citations,
        "web_results": web_citations,
        "react_iteration_count": iteration,
        "final_answer": final_answer,
        "source_type": source_type,
        "supplementary_resources": supplementary_resources,
        "error": None,
    }
