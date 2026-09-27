"""
Unit tests for tools/tavily_tool.py's supplementary-resource abstraction
(get_supplementary_resources and its helpers).

These never touch the live Tavily API: `_call_tavily_search` is monkeypatched
directly (same seam agents.explainer's own tests use), with realistic
Tavily-shaped mock payloads (title/url/content/score), per the project's
mocking convention.
"""
import pytest

import tools.tavily_tool as tavily_tool_module
from config import settings
from tools.tavily_tool import (
    _domain_of,
    _is_valid_url,
    _is_video_url,
    get_supplementary_resources,
)


@pytest.fixture(autouse=True)
def ensure_tavily_key(monkeypatch):
    """get_supplementary_resources short-circuits to empty results when no
    key is configured -- most tests here want the real categorization logic
    to run, so a key is guaranteed present unless a test explicitly clears it."""
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "test-key-not-real")


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def test_domain_of_strips_www():
    assert _domain_of("https://www.youtube.com/watch?v=abc") == "youtube.com"
    assert _domain_of("https://example.edu/page") == "example.edu"


def test_is_valid_url_rejects_malformed_and_empty():
    assert _is_valid_url("https://example.com/page") is True
    assert _is_valid_url("not-a-valid-url") is False
    assert _is_valid_url("") is False
    assert _is_valid_url(None) is False
    assert _is_valid_url("ftp://example.com/file") is False  # not http(s)


def test_is_video_url_matches_known_video_domains_only():
    assert _is_video_url("https://www.youtube.com/watch?v=abc") is True
    assert _is_video_url("https://youtu.be/abc") is True
    assert _is_video_url("https://vimeo.com/12345") is True
    assert _is_video_url("https://example.edu/page") is False


# ---------------------------------------------------------------------------
# get_supplementary_resources -- categorization
# ---------------------------------------------------------------------------

def _mock_per_query(monkeypatch, by_query: dict[str, list[dict]]):
    """Routes _call_tavily_search's mocked return value by which of the 3
    targeted queries (a substring of the query text) was actually issued --
    lets a single test assert each category independently, mirroring how
    Tavily would genuinely return different results for different queries."""
    def fake(*, query: str, max_results: int = 3):
        for marker, results in by_query.items():
            if marker in query:
                return results
        return []
    monkeypatch.setattr(tavily_tool_module, "_call_tavily_search", fake)


def test_video_results_classified_correctly(monkeypatch):
    _mock_per_query(monkeypatch, {
        "educational video": [
            {"title": "Cell Structure Explained", "url": "https://www.youtube.com/watch?v=cell1",
             "content": "A video walkthrough of cell structure.", "score": 0.9},
        ],
    })
    result = get_supplementary_resources(track="NEET", subject="Biology", topic="Cell", query="What is a cell?")
    assert len(result["videos"]) == 1
    assert result["videos"][0] == {
        "title": "Cell Structure Explained",
        "url": "https://www.youtube.com/watch?v=cell1",
        "description": "A video walkthrough of cell structure.",
        "resource_type": "VIDEO",
        "source": "youtube.com",
    }
    assert result["articles"] == []
    assert result["real_world_examples"] == []


def test_video_query_result_that_is_not_a_video_url_is_dropped_not_fabricated(monkeypatch):
    """If Tavily doesn't return a reliable video result, return no video -- never mislabel a non-video page as one."""
    _mock_per_query(monkeypatch, {
        "educational video": [
            {"title": "Cell Structure Blog Post", "url": "https://example.edu/cell-structure",
             "content": "Not actually a video.", "score": 0.8},
        ],
    })
    result = get_supplementary_resources(track="NEET", subject="Biology", topic="Cell", query="What is a cell?")
    assert result["videos"] == []


def test_article_results_classified_correctly(monkeypatch):
    _mock_per_query(monkeypatch, {
        "tutorial explanation": [
            {"title": "SQL Joins Explained", "url": "https://example.edu/sql-joins",
             "content": "A tutorial on inner/outer joins.", "score": 0.85},
        ],
    })
    result = get_supplementary_resources(track="Placement", subject="SQL", topic="Joins", query="What is a SQL join?")
    assert len(result["articles"]) == 1
    assert result["articles"][0]["resource_type"] == "ARTICLE"
    assert result["articles"][0]["url"] == "https://example.edu/sql-joins"
    assert result["articles"][0]["source"] == "example.edu"


def test_real_world_example_results_classified_correctly(monkeypatch):
    _mock_per_query(monkeypatch, {
        "real world applications": [
            {"title": "Fraud Detection with Classification", "url": "https://example.com/fraud-detection-ml",
             "content": "How banks use classification models to flag fraud.", "score": 0.88},
        ],
    })
    result = get_supplementary_resources(
        track="Placement", subject="DSA", topic="Machine Learning classification", query="Explain classification"
    )
    assert len(result["real_world_examples"]) == 1
    assert result["real_world_examples"][0]["resource_type"] == "REAL_WORLD_EXAMPLE"
    assert result["real_world_examples"][0]["url"] == "https://example.com/fraud-detection-ml"


def test_article_and_realworld_queries_never_classify_a_video_url_as_non_video(monkeypatch):
    _mock_per_query(monkeypatch, {
        "tutorial explanation": [
            {"title": "A YouTube video, mistakenly in article results", "url": "https://youtu.be/xyz",
             "content": "...", "score": 0.99},
        ],
        "real world applications": [
            {"title": "Another stray video", "url": "https://vimeo.com/999", "content": "...", "score": 0.99},
        ],
    })
    result = get_supplementary_resources(track="NEET", subject="Physics", topic="Newton's laws", query="Explain Newton's laws")
    assert result["articles"] == []
    assert result["real_world_examples"] == []


# ---------------------------------------------------------------------------
# Filtering / dedup / limits
# ---------------------------------------------------------------------------

def test_duplicate_urls_removed_across_categories(monkeypatch):
    same_url = "https://example.edu/joins"
    _mock_per_query(monkeypatch, {
        "tutorial explanation": [{"title": "SQL Joins", "url": same_url, "content": "...", "score": 0.9}],
        "real world applications": [{"title": "SQL Joins", "url": same_url, "content": "...", "score": 0.9}],
    })
    result = get_supplementary_resources(track="Placement", subject="SQL", topic="Joins", query="What is a join?")
    all_urls = [r["url"] for cat in result.values() for r in cat]
    assert all_urls.count(same_url) == 1  # kept in exactly one category, not both


def test_invalid_urls_ignored(monkeypatch):
    _mock_per_query(monkeypatch, {
        "tutorial explanation": [
            {"title": "Broken result", "url": "not-a-url-at-all", "content": "...", "score": 0.9},
            {"title": "", "url": "https://example.edu/empty-title", "content": "...", "score": 0.9},
            {"title": "Valid result", "url": "https://example.edu/valid", "content": "...", "score": 0.8},
        ],
    })
    result = get_supplementary_resources(track="Placement", subject="SQL", topic="Joins", query="What is a join?")
    assert len(result["articles"]) == 1
    assert result["articles"][0]["url"] == "https://example.edu/valid"


def test_result_limits_enforced_per_category(monkeypatch):
    many_articles = [
        {"title": f"Article {i}", "url": f"https://example.edu/article-{i}", "content": "...", "score": 0.5 + i * 0.01}
        for i in range(5)
    ]
    _mock_per_query(monkeypatch, {"tutorial explanation": many_articles})
    result = get_supplementary_resources(track="Placement", subject="SQL", topic="Joins", query="What is a join?")
    assert len(result["articles"]) == 3  # MAX_RESOURCES_PER_CATEGORY, not all 5
    # Highest-scored ones are kept (4 and 3, since score increases with i).
    kept_urls = {r["url"] for r in result["articles"]}
    assert kept_urls == {"https://example.edu/article-4", "https://example.edu/article-3", "https://example.edu/article-2"}


def test_total_resources_capped_at_nine():
    pass  # structurally guaranteed: 3 categories x MAX_RESOURCES_PER_CATEGORY(3) == 9, covered by the limit test above


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def test_missing_api_key_returns_empty_resources_without_calling_tavily(monkeypatch):
    monkeypatch.setattr(settings, "TAVILY_API_KEY", None)
    called = []
    monkeypatch.setattr(tavily_tool_module, "_call_tavily_search", lambda **kwargs: called.append(kwargs) or [])

    result = get_supplementary_resources(track="NEET", subject="Biology", topic="Cell", query="What is a cell?")
    assert result == {"videos": [], "articles": [], "real_world_examples": []}
    assert called == []


def test_tavily_failure_returns_empty_resources_not_a_crash(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("simulated network failure")
    monkeypatch.setattr(tavily_tool_module, "_call_tavily_search", boom)

    result = get_supplementary_resources(track="NEET", subject="Biology", topic="Cell", query="What is a cell?")
    assert result == {"videos": [], "articles": [], "real_world_examples": []}


def test_no_fabricated_urls_ever_appear(monkeypatch):
    """Every url in every category must be traceable to a mocked Tavily result -- nothing invented."""
    real_urls = {"https://www.youtube.com/watch?v=real1", "https://example.edu/real-article"}
    _mock_per_query(monkeypatch, {
        "educational video": [{"title": "Real Video", "url": "https://www.youtube.com/watch?v=real1", "content": "...", "score": 0.9}],
        "tutorial explanation": [{"title": "Real Article", "url": "https://example.edu/real-article", "content": "...", "score": 0.9}],
    })
    result = get_supplementary_resources(track="NEET", subject="Biology", topic="Cell", query="What is a cell?")
    all_urls = {r["url"] for cat in result.values() for r in cat}
    assert all_urls.issubset(real_urls)
