#!/usr/bin/env python
"""
CLI: query the RAG knowledge base and print retrieved chunks + citations.

No LLM is called here -- Phase 3 only retrieves and cites source material.
Turning this into a spoken explanation is a later (Explainer agent) phase.

Example:
    python scripts/query_rag.py \\
        --track NEET --subject Biology --query "What is the function of mitochondria?"
"""
import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag.loader import TRACK_SUBJECTS  # noqa: E402
from rag.retriever import retrieve  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the Adaptive AI Study Tutor RAG knowledge base.")
    parser.add_argument("--track", required=True, choices=sorted(TRACK_SUBJECTS.keys()))
    parser.add_argument("--subject", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--topic", default=None, help="Optional chapter/topic filter")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--score-threshold", type=float, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        result = retrieve(
            query=args.query,
            track=args.track,
            subject=args.subject,
            topic=args.topic,
            top_k=args.top_k,
            score_threshold=args.score_threshold,
        )
    except ValueError as exc:
        print(f"Query rejected: {exc}")
        sys.exit(1)

    print("Query:")
    print(result.query)
    print()
    print(f"Track: {result.track}")
    print(f"Subject: {result.subject}")
    if result.topic:
        print(f"Topic: {result.topic}")
    print()

    if not result.sufficient:
        print("RAG could not find sufficiently relevant source material.")
        print("(No answer generated -- this is the 'insufficient retrieval' signal a later")
        print(" phase will use to fall back to Tavily web search.)")
        return

    print("Retrieved:")
    for i, doc in enumerate(result.documents, start=1):
        meta = doc.metadata
        print(f"{i}. score={doc.score}")
        print(f"   Source: {meta.get('source')}")
        print(f"   Document: {meta.get('document_name')}")
        print(f"   Page: {meta.get('page')}")
        print(f"   Chapter: {meta.get('chapter')}")
    print()

    print("Citations:")
    for citation in result.citations:
        page_part = f"p. {citation.page}" if citation.page is not None else "page unknown"
        chapter_part = citation.chapter or "chapter unknown"
        print(f"[{citation.source} | {citation.subject} | {chapter_part} | {page_part}]")


if __name__ == "__main__":
    main()
