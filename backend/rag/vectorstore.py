"""
ChromaDB persistence layer.

Two physically separate collections -- neet_kb and placement_kb -- rather
than one collection with a track filter. This makes track separation
structural: a bug in a metadata filter can never leak Placement chunks into
a NEET retrieval, because a NEET query is never even pointed at the
placement_kb collection.

This module only knows about storage (get/add/dedupe). It has no awareness
of agents, quizzes, or anything from later phases -- it will be reused as-is
by the MCP server's tools in Phase 4.

Deduplication / idempotency strategy
-------------------------------------
Every chunk's ID is a deterministic SHA-256 hash of
(track, subject, source, document_name, page, chunk_index, content-hash).
Re-ingesting the exact same document with the exact same chunking
configuration reproduces the exact same IDs. Before inserting, we check
which of the newly computed IDs already exist in the target collection
(`collection.get(ids=...)`) and only add the ones that don't -- so
re-running ingestion on an already-ingested document inserts zero
duplicate chunks (see add_chunks()).
"""
import hashlib
from dataclasses import dataclass
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import settings
from rag.embeddings import get_embedding_model
from rag.loader import validate_track

COLLECTION_NAMES: dict[str, str] = {
    "NEET": "neet_kb",
    "Placement": "placement_kb",
}


def get_collection_name(track: str) -> str:
    validate_track(track)
    return COLLECTION_NAMES[track]


@lru_cache(maxsize=None)
def get_vectorstore(track: str) -> Chroma:
    """
    Returns the persistent Chroma collection for a track, cached per track
    so the same client/collection object is reused across calls instead of
    re-opening the on-disk store for every ingestion or query.
    """
    collection_name = get_collection_name(track)
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding_model(),
        persist_directory=str(settings.chroma_persist_path),
        # Cosine distance is bounded and easy to convert to a similarity
        # score (see rag/retriever.py) -- this must match the space used
        # for the embeddings normalize_embeddings=True in rag/embeddings.py.
        collection_metadata={"hnsw:space": "cosine"},
    )


def build_chunk_id(metadata: dict, content: str) -> str:
    """Deterministic chunk ID -- see module docstring for the dedup strategy this enables."""
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    key_parts = [
        str(metadata.get("track", "")),
        str(metadata.get("subject", "")),
        str(metadata.get("source", "")),
        str(metadata.get("document_name", "")),
        str(metadata.get("page", "")),
        str(metadata.get("chunk_index", "")),
        content_hash,
    ]
    raw_key = "|".join(key_parts)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@dataclass
class IngestionOutcome:
    inserted: int
    duplicates_skipped: int
    collection: str


def add_chunks(track: str, chunks: list[Document]) -> IngestionOutcome:
    """Insert chunks into the track's collection, skipping any whose deterministic ID already exists."""
    collection_name = get_collection_name(track)
    if not chunks:
        return IngestionOutcome(inserted=0, duplicates_skipped=0, collection=collection_name)

    vectorstore = get_vectorstore(track)

    ids: list[str] = []
    for chunk in chunks:
        chunk_id = build_chunk_id(chunk.metadata, chunk.page_content)
        chunk.metadata["chunk_id"] = chunk_id
        ids.append(chunk_id)

    existing = vectorstore.get(ids=ids)
    existing_ids = set(existing.get("ids", []))

    new_chunks = [c for c, cid in zip(chunks, ids) if cid not in existing_ids]
    new_ids = [cid for cid in ids if cid not in existing_ids]

    if new_chunks:
        vectorstore.add_documents(new_chunks, ids=new_ids)

    return IngestionOutcome(
        inserted=len(new_chunks),
        duplicates_skipped=len(chunks) - len(new_chunks),
        collection=collection_name,
    )


def build_where_filter(subject: str, topic: str | None) -> dict:
    """
    Chroma's `where` filter requires an explicit "$and" for more than one
    top-level condition (a bare multi-key dict is rejected by recent Chroma
    versions) -- this always returns a filter shape Chroma accepts.
    """
    conditions = [{"subject": subject}]
    if topic:
        conditions.append({"chapter": topic})
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def similarity_search(track: str, query: str, where: dict, top_k: int) -> list[tuple[Document, float]]:
    """Returns (Document, cosine_distance) pairs -- see rag/retriever.py for the distance->score conversion."""
    vectorstore = get_vectorstore(track)
    return vectorstore.similarity_search_with_score(query, k=top_k, filter=where)
