"""
Text cleaning and chunking.

Cleaning here is deliberately conservative: it collapses obvious PDF-
extraction noise (runs of whitespace, excessive blank lines) and does
nothing else. It never rewrites, paraphrases, or otherwise alters textbook
wording, formulas, or code examples -- the RAG system must retrieve the
source text, not a reinterpretation of it.
"""
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings


def clean_text(text: str) -> str:
    """Whitespace/artifact cleanup only -- content and wording are untouched."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)          # collapse 3+ blank lines to one
    text = re.sub(r"[ \t]{2,}", " ", text)           # collapse repeated spaces/tabs
    text = "\n".join(line.rstrip() for line in text.split("\n"))  # trailing whitespace per line
    return text.strip()


def get_text_splitter(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.CHUNK_SIZE,
        chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def split_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Document]:
    """
    Clean each page's text, then chunk with RecursiveCharacterTextSplitter.
    Every resulting chunk keeps its source page's metadata plus a
    `chunk_index` counter that restarts at 0 for each document_name -- this
    keeps chunk IDs (see rag/vectorstore.py) stable across repeated
    ingestion runs of the same document.
    """
    cleaned_docs = [
        Document(page_content=clean_text(doc.page_content), metadata=dict(doc.metadata))
        for doc in documents
        if doc.page_content and doc.page_content.strip()
    ]

    splitter = get_text_splitter(chunk_size, chunk_overlap)
    chunks = splitter.split_documents(cleaned_docs)

    chunk_counters: dict[str, int] = {}
    for chunk in chunks:
        document_name = chunk.metadata.get("document_name", "unknown")
        idx = chunk_counters.get(document_name, 0)
        chunk.metadata["chunk_index"] = idx
        chunk_counters[document_name] = idx + 1

    return chunks
