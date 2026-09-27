"""
Embedding model loading.

Model: sentence-transformers/all-MiniLM-L6-v2 (configurable via
EMBEDDING_MODEL) -- a 384-dimension sentence-transformer that runs locally
via HuggingFace/torch, with no external embedding API call.

get_embedding_model() is cached (functools.lru_cache) so the model is loaded
into memory exactly once per process and reused for every ingestion and
query call, rather than re-initializing torch/sentence-transformers on every
request.
"""
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=settings.EMBEDDING_MODEL,
        # Normalized embeddings make cosine distance behave predictably
        # (bounded ~[0, 2]), which is what rag/retriever.py's
        # distance-to-similarity conversion assumes.
        encode_kwargs={"normalize_embeddings": True},
    )
