"""
The reusable RAG retriever.

This is the module Explainer/Quiz Master/MCP tools will call in later
phases -- it is intentionally decoupled from all of them (no agent, prompt,
or LLM logic lives here). Phase 3 stops at "retrieved context + citations";
turning that into a spoken explanation is Phase 5's job.

Distance -> similarity score conversion (read this before changing it)
------------------------------------------------------------------------
Chroma's `similarity_search_with_score` returns a *distance*, not a
similarity -- and the distance's meaning depends on the collection's
configured space. This project explicitly sets every collection's space to
cosine (`collection_metadata={"hnsw:space": "cosine"}`, see
rag/vectorstore.py) and normalizes every embedding vector before it is
stored (`normalize_embeddings=True`, see rag/embeddings.py). Under those two
conditions, Chroma's cosine distance is `1 - cosine_similarity`, bounded to
approximately [0, 2] (0 = identical direction, 1 = orthogonal, 2 = opposite).

So: similarity_score = 1 - distance.

This is NOT a generic fact about Chroma -- if the space were left as the
default squared-L2, or embeddings were not normalized, this formula would be
wrong. Anyone changing the embedding or collection configuration must revisit
this conversion.
"""
from typing import Optional

from pydantic import BaseModel, Field

from config import settings
from rag.loader import validate_subject, validate_track
from rag.vectorstore import build_where_filter, similarity_search


class Citation(BaseModel):
    source: str
    track: str
    subject: str
    document_name: str
    chapter: Optional[str] = None
    page: Optional[int] = None


class RetrievedDocument(BaseModel):
    content: str
    metadata: dict
    score: float


class RetrievalResult(BaseModel):
    query: str
    track: str
    subject: str
    topic: Optional[str] = None
    sufficient: bool
    documents: list[RetrievedDocument] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


def _citation_from_metadata(metadata: dict, *, fallback_track: str, fallback_subject: str) -> Citation:
    """
    Builds a citation strictly from the chunk's own stored metadata. Nothing
    here is invented: a missing page/chapter becomes None (rendered as
    "unknown"/null downstream), never a guessed value.
    """
    return Citation(
        source=metadata.get("source", "OTHER"),
        track=metadata.get("track", fallback_track),
        subject=metadata.get("subject", fallback_subject),
        document_name=metadata.get("document_name", "unknown"),
        chapter=metadata.get("chapter"),
        page=metadata.get("page"),
    )


def retrieve(
    query: str,
    track: str,
    subject: str,
    topic: Optional[str] = None,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
) -> RetrievalResult:
    """
    Retrieve grounded context for a query, scoped to exactly one track's
    collection and one subject.

    track="NEET" only ever searches the neet_kb collection; track="Placement"
    only ever searches placement_kb. There is no code path in this function
    that can query the other track's collection.
    """
    validate_subject(track, subject)  # raises if track is unknown or subject doesn't belong to it

    k = top_k or settings.RAG_TOP_K
    threshold = settings.RAG_SCORE_THRESHOLD if score_threshold is None else score_threshold

    where = build_where_filter(subject, topic)
    raw_results = similarity_search(track, query, where, k)

    documents: list[RetrievedDocument] = []
    citations: list[Citation] = []

    for doc, distance in raw_results:
        similarity = 1.0 - distance  # see module docstring
        if similarity < threshold:
            continue
        documents.append(RetrievedDocument(content=doc.page_content, metadata=doc.metadata, score=round(similarity, 4)))
        citations.append(_citation_from_metadata(doc.metadata, fallback_track=track, fallback_subject=subject))

    return RetrievalResult(
        query=query,
        track=track,
        subject=subject,
        topic=topic,
        sufficient=len(documents) > 0,
        documents=documents,
        citations=citations,
    )
