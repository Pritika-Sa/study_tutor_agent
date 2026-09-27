"""
Tavily web search -- the supplementary (never-first) source, per the
architecture's RAG-first rule: only called when RAG is insufficient or the
question needs current/up-to-date information the knowledge base can't have.

Real Tavily call is isolated in `_call_tavily_search` specifically so tests
can monkeypatch it. Every returned result's `url` is exactly what Tavily
returned; nothing here invents or reformats a URL.

Failure handling: Tavily is explicitly supplementary, never required -- any
failure (empty query, network error, rate limit, timeout, bad request) is
caught and logged, degrading to "no web results" rather than crashing the
whole /tutor/ask request. Caught for real: the adaptive retry loop's
internal re-explanation call reaches the Explainer with an empty
`user_query` (quiz flows never populate one -- see agents/evaluator.py's
fix), and the live Tavily API correctly rejected that with "Query is
missing." before this try/except existed.
"""
import logging
from typing import Optional
from urllib.parse import urlparse

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)


def _call_tavily_search(*, query: str, max_results: int = 3) -> list[dict]:
    if not settings.TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY is not configured -- web search unavailable, returning no results.")
        return []

    if not query or not query.strip():
        logger.warning("Tavily search skipped: empty query.")
        return []

    from tavily import TavilyClient  # imported lazily: a missing/unused key never breaks module import

    client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    try:
        response = client.search(query=query, max_results=max_results)
    except Exception as exc:  # noqa: BLE001 -- any Tavily-side failure degrades to "no web results", never crashes the request
        logger.warning("Tavily search failed (%s) -- continuing without web results.", exc)
        return []

    results = []
    for item in response.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            # Tavily's own relevance score -- used by get_supplementary_resources
            # below to prefer higher-quality results without a hardcoded domain
            # allowlist. Additive only: every existing caller of this function
            # (agents/explainer.py's primary web-fallback path) reads title/
            # url/content and simply ignores this extra key.
            "score": item.get("score", 0.0),
        })
    return results


# ---------------------------------------------------------------------------
# Supplementary learning resources (videos / articles / real-world examples).
#
# Reuses _call_tavily_search above -- the same Tavily client, the same
# failure-handling philosophy (never raises; degrades to empty results) --
# rather than standing up a second Tavily integration. This is a distinct
# capability from the ReAct fallback's single generic query: it always runs
# up to 3 *targeted* searches (one per resource type) so results are
# naturally pre-categorized by which query found them, rather than needing an
# LLM (or a hardcoded domain allowlist) to guess a generic result's category.
# ---------------------------------------------------------------------------

MAX_RESOURCES_PER_CATEGORY = 3
CANDIDATE_RESULTS_PER_QUERY = 5  # fetched before filtering/limiting, so a few low-quality hits don't starve a category
DESCRIPTION_MAX_CHARS = 200
VIDEO_DOMAINS = {"youtube.com", "youtu.be", "vimeo.com"}

EMPTY_SUPPLEMENTARY_RESOURCES = {"videos": [], "articles": [], "real_world_examples": []}


def _domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return ""
    return netloc[4:] if netloc.startswith("www.") else netloc


def _is_valid_url(url: str) -> bool:
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _is_video_url(url: str) -> bool:
    return _domain_of(url) in VIDEO_DOMAINS


def _truncate(text: str, limit: int = DESCRIPTION_MAX_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _to_resource(item: dict, resource_type: str) -> Optional[dict]:
    """
    Normalizes one raw Tavily result into the resource shape. Returns None
    (dropped, never fabricated) for anything without a real title or a
    valid http(s) URL -- an invalid/empty/malformed URL never becomes a
    resource, per the "never fabricate a URL" rule.
    """
    url = item.get("url", "")
    title = (item.get("title") or "").strip()
    if not _is_valid_url(url) or not title:
        return None
    return {
        "title": title,
        "url": url,
        "description": _truncate(item.get("content", "")),
        "resource_type": resource_type,
        "source": _domain_of(url) or url,
        "_score": item.get("score") or 0.0,  # internal only -- stripped before returning
    }


def _select_top(candidates: list[dict], limit: int, seen_urls: set, seen_titles: set) -> list[dict]:
    """
    Sorts by Tavily's own relevance score (the non-hardcoded "domain
    quality" signal -- see module docstring), then keeps the first `limit`
    that aren't a duplicate URL or title of something already selected in
    ANY category (a resource already shown as a video is never repeated as
    an article, etc.). `seen_urls`/`seen_titles` are shared across all three
    categories by the caller.
    """
    ranked = sorted(candidates, key=lambda r: r["_score"], reverse=True)
    kept = []
    for resource in ranked:
        url_key = resource["url"].rstrip("/").lower()
        title_key = resource["title"].strip().lower()
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        kept.append({k: v for k, v in resource.items() if k != "_score"})
        if len(kept) >= limit:
            break
    return kept


def _build_supplementary_queries(*, track: str, subject: str, topic: Optional[str], query: str) -> dict[str, str]:
    """
    Dynamically built from the student's actual context -- never a
    hardcoded subject/topic. Combines subject + topic (when both are given)
    rather than the bare topic alone: a lone one-word topic like "Cell" or
    "Joins" is ambiguous to a generic web search (observed live: "Cell"
    alone pulled fuel-cell/battery results instead of biology), whereas
    "Biology Cell" or "SQL Joins" disambiguates it. Falls back to subject
    alone, then the raw question, exactly mirroring agents/explainer.py's
    own RAG-widening precedence.
    """
    if topic and subject:
        label = f"{subject} {topic}".strip()
    else:
        label = (topic or subject or query or "").strip()
    # Track awareness (section 22): a Placement question is realistically
    # being studied for a technical interview, so nudge the tutorial/article
    # search toward that framing; NEET has no equivalent real-world-exam
    # framing to add, so it's left as the plain query.
    interview_hint = " for technical interview preparation" if track == "Placement" else ""
    return {
        "VIDEO": f"{label} educational video",
        "ARTICLE": f"{label} tutorial explanation{interview_hint}",
        "REAL_WORLD_EXAMPLE": f"{label} real world applications examples",
    }


def get_supplementary_resources(*, track: str, subject: str, topic: Optional[str], query: str) -> dict:
    """
    Runs up to 3 bounded, targeted Tavily searches (never a loop, never
    recursive -- see graph/ for the actual ReAct bound, which this is
    entirely separate from) and returns a normalized, deduplicated,
    category-capped resource set:

        {"videos": [...], "articles": [...], "real_world_examples": [...]}

    Every resource's `url` is exactly what Tavily returned -- nothing here
    ever invents a URL. Any failure (missing key, network error, timeout,
    malformed response) degrades to EMPTY_SUPPLEMENTARY_RESOURCES, matching
    _call_tavily_search's own "supplementary, never required" philosophy --
    this must never be the reason a /tutor/ask request fails.
    """
    if not settings.TAVILY_API_KEY:
        return {k: list(v) for k, v in EMPTY_SUPPLEMENTARY_RESOURCES.items()}

    try:
        queries = _build_supplementary_queries(track=track, subject=subject, topic=topic, query=query)

        video_raw = _call_tavily_search(query=queries["VIDEO"], max_results=CANDIDATE_RESULTS_PER_QUERY)
        article_raw = _call_tavily_search(query=queries["ARTICLE"], max_results=CANDIDATE_RESULTS_PER_QUERY)
        realworld_raw = _call_tavily_search(query=queries["REAL_WORLD_EXAMPLE"], max_results=CANDIDATE_RESULTS_PER_QUERY)

        seen_urls: set = set()
        seen_titles: set = set()

        # Video query results that aren't actually a video URL are dropped
        # entirely rather than reclassified -- "if Tavily does not return a
        # reliable video result, simply return no video".
        video_candidates = [r for r in (_to_resource(i, "VIDEO") for i in video_raw) if r and _is_video_url(r["url"])]
        videos = _select_top(video_candidates, MAX_RESOURCES_PER_CATEGORY, seen_urls, seen_titles)

        article_candidates = [
            r for r in (_to_resource(i, "ARTICLE") for i in article_raw) if r and not _is_video_url(r["url"])
        ]
        articles = _select_top(article_candidates, MAX_RESOURCES_PER_CATEGORY, seen_urls, seen_titles)

        realworld_candidates = [
            r for r in (_to_resource(i, "REAL_WORLD_EXAMPLE") for i in realworld_raw) if r and not _is_video_url(r["url"])
        ]
        real_world_examples = _select_top(realworld_candidates, MAX_RESOURCES_PER_CATEGORY, seen_urls, seen_titles)

        return {"videos": videos, "articles": articles, "real_world_examples": real_world_examples}
    except Exception as exc:  # noqa: BLE001 -- supplementary resources must never break the primary tutor answer
        logger.warning("Supplementary resource search failed (%s) -- returning no resources.", exc)
        return {k: list(v) for k, v in EMPTY_SUPPLEMENTARY_RESOURCES.items()}


class TavilySearchInput(BaseModel):
    query: str = Field(description="The web search query.")
    max_results: int = Field(default=3, ge=1, le=10)


@tool("tavily_web_search", args_schema=TavilySearchInput)
def tavily_web_search(query: str, max_results: int = 3) -> list[dict]:
    """
    Search the live web via Tavily for current or supplementary information.
    Use only when the RAG knowledge base is insufficient, or the question
    explicitly needs current/recent information the knowledge base cannot
    contain. Each result has title, url, and content -- the url is always
    exactly what Tavily returned, never invented.
    """
    return _call_tavily_search(query=query, max_results=max_results)
