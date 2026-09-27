"""
RAG pipeline test suite for Phase 3.

Uses a hand-built minimal PDF (see _make_simple_pdf below) and an isolated
temporary Chroma directory per test -- the real data/chroma/ knowledge base
is never touched by these tests. The synthetic PDF content is clearly
labelled as test material and is never represented as NCERT/NPTEL.
"""
from pathlib import Path

import pytest
from langchain_core.documents import Document

from rag.loader import (
    LoadFailure,
    load_directory,
    load_pdf,
    validate_subject,
    validate_track,
)
from rag.splitter import clean_text, split_documents
from rag.vectorstore import build_chunk_id, add_chunks, get_collection_name, get_vectorstore
from rag.retriever import retrieve


# ---------------------------------------------------------------------------
# Isolation: every test gets its own temp Chroma directory and a cleared
# vectorstore cache, so tests never see each other's inserted chunks and
# never touch the real data/chroma/ knowledge base.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_chroma(tmp_path):
    from config import settings
    from rag import vectorstore as vectorstore_module

    settings.CHROMA_PERSIST_DIRECTORY = str(tmp_path / "chroma_test")
    vectorstore_module.get_vectorstore.cache_clear()
    yield
    vectorstore_module.get_vectorstore.cache_clear()


# ---------------------------------------------------------------------------
# Synthetic PDF builder (no external PDF-writing dependency needed)
# ---------------------------------------------------------------------------

def _make_simple_pdf(path: Path, lines: list[str]) -> None:
    """Builds a minimal, valid single-page PDF by hand. Test fixture only -- never NCERT/NPTEL."""
    content_lines = []
    y = 750
    for line in lines:
        safe = line.replace("(", r"\(").replace(")", r"\)")
        content_lines.append(f"BT /F1 12 Tf 72 {y} Td ({safe}) Tj ET")
        y -= 20
    content_stream = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        (f"<< /Length {len(content_stream)} >>\nstream\n").encode("latin-1") + content_stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    buf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj_body in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode("latin-1")
        buf += obj_body
        buf += b"\nendobj\n"

    xref_offset = len(buf)
    buf += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    buf += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        buf += f"{off:010d} 00000 n \n".encode("latin-1")
    buf += b"trailer\n"
    buf += f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("latin-1")
    buf += b"startxref\n"
    buf += f"{xref_offset}\n".encode("latin-1")
    buf += b"%%EOF"

    path.write_bytes(bytes(buf))


# ---------------------------------------------------------------------------
# Track / subject validation
# ---------------------------------------------------------------------------

def test_validate_track_rejects_unknown_track():
    with pytest.raises(ValueError):
        validate_track("Medicine")


def test_validate_subject_rejects_mismatched_track():
    # Physics is a NEET subject, not a Placement one
    with pytest.raises(ValueError):
        validate_subject("Placement", "Physics")


# ---------------------------------------------------------------------------
# Loader: PDF extraction, page metadata, failure reporting
# ---------------------------------------------------------------------------

def test_load_pdf_extracts_text_and_preserves_metadata(tmp_path):
    pdf_path = tmp_path / "sample_biology.pdf"
    _make_simple_pdf(pdf_path, ["SYNTHETIC TEST CONTENT - not NCERT", "Mitochondria is the powerhouse of the cell."])

    documents, failure = load_pdf(pdf_path, track="NEET", subject="Biology", source="NCERT", chapter="Cell Structure")

    assert failure is None
    assert len(documents) == 1
    doc = documents[0]
    assert "Mitochondria is the powerhouse of the cell." in doc.page_content
    assert doc.metadata["track"] == "NEET"
    assert doc.metadata["subject"] == "Biology"
    assert doc.metadata["source"] == "NCERT"
    assert doc.metadata["document_name"] == "sample_biology.pdf"
    assert doc.metadata["page"] == 1  # 0-indexed internally, stored 1-indexed
    assert doc.metadata["chapter"] == "Cell Structure"


def test_load_pdf_chapter_defaults_to_none_when_not_supplied(tmp_path):
    pdf_path = tmp_path / "sample_no_chapter.pdf"
    _make_simple_pdf(pdf_path, ["Some content."])

    documents, failure = load_pdf(pdf_path, track="Placement", subject="DBMS", source="NPTEL")

    assert failure is None
    assert documents[0].metadata["chapter"] is None  # never fabricated


def test_load_directory_reports_failure_and_continues(tmp_path):
    good_pdf = tmp_path / "good.pdf"
    _make_simple_pdf(good_pdf, ["Readable content."])

    broken_pdf = tmp_path / "broken.pdf"
    broken_pdf.write_bytes(b"not a real pdf file")

    result = load_directory(tmp_path, track="NEET", subject="Physics", source="NCERT")

    assert len(result.discovered_files) == 2
    assert len(result.processed_files) == 1
    assert len(result.failures) == 1
    assert isinstance(result.failures[0], LoadFailure)
    assert "broken.pdf" in result.failures[0].file_path


# ---------------------------------------------------------------------------
# Splitter: cleaning + chunking + metadata preservation
# ---------------------------------------------------------------------------

def test_clean_text_collapses_whitespace_without_altering_words():
    dirty = "Photosynthesis   is\n\n\n\nthe    process.\n\n\n"
    cleaned = clean_text(dirty)
    assert "Photosynthesis is" in cleaned
    assert "\n\n\n" not in cleaned
    assert "process." in cleaned


def test_split_documents_preserves_metadata_and_assigns_chunk_index():
    long_text = "Normalization removes redundancy. " * 100
    doc = Document(page_content=long_text, metadata={"document_name": "dbms.pdf", "track": "Placement", "subject": "DBMS", "page": 42})

    chunks = split_documents([doc], chunk_size=200, chunk_overlap=20)

    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.metadata["document_name"] == "dbms.pdf"
        assert chunk.metadata["subject"] == "DBMS"
        assert chunk.metadata["chunk_index"] == i


# ---------------------------------------------------------------------------
# Vectorstore: deterministic IDs, dedup/idempotency, collection separation
# ---------------------------------------------------------------------------

def test_build_chunk_id_is_deterministic_and_content_sensitive():
    metadata = {"track": "NEET", "subject": "Biology", "source": "NCERT", "document_name": "bio.pdf", "page": 1, "chunk_index": 0}

    id_a = build_chunk_id(metadata, "Mitochondria is the powerhouse of the cell.")
    id_b = build_chunk_id(metadata, "Mitochondria is the powerhouse of the cell.")
    id_c = build_chunk_id(metadata, "Different content entirely.")

    assert id_a == id_b
    assert id_a != id_c


def test_ingestion_is_idempotent_no_duplicate_chunks():
    doc = Document(
        page_content="Normalization removes redundancy in relational databases.",
        metadata={"track": "Placement", "subject": "DBMS", "source": "NPTEL", "document_name": "dbms.pdf", "page": 42, "chapter": "Normalization", "chunk_index": 0},
    )

    first = add_chunks("Placement", [doc])
    assert first.inserted == 1
    assert first.duplicates_skipped == 0

    second = add_chunks("Placement", [doc])  # re-ingest the exact same chunk
    assert second.inserted == 0
    assert second.duplicates_skipped == 1


def test_neet_and_placement_use_separate_collections():
    assert get_collection_name("NEET") == "neet_kb"
    assert get_collection_name("Placement") == "placement_kb"
    assert get_vectorstore("NEET") is not get_vectorstore("Placement")


def test_track_isolation_placement_query_never_returns_neet_content():
    neet_doc = Document(
        page_content="Mitochondria is the powerhouse of the cell.",
        metadata={"track": "NEET", "subject": "Biology", "source": "NCERT", "document_name": "bio.pdf", "page": 120, "chapter": "Cell Structure", "chunk_index": 0},
    )
    placement_doc = Document(
        page_content="A primary key uniquely identifies each row in a relational table.",
        metadata={"track": "Placement", "subject": "DBMS", "source": "NPTEL", "document_name": "dbms.pdf", "page": 10, "chapter": "Keys", "chunk_index": 0},
    )
    add_chunks("NEET", [neet_doc])
    add_chunks("Placement", [placement_doc])

    result = retrieve(query="What is the function of mitochondria?", track="Placement", subject="DBMS", score_threshold=0.0)

    contents = [d.content for d in result.documents]
    assert "Mitochondria is the powerhouse of the cell." not in contents


# ---------------------------------------------------------------------------
# Retriever: subject filtering, citations, insufficient-retrieval signal, semantic search
# ---------------------------------------------------------------------------

def test_subject_filtering_excludes_other_subjects_in_same_track():
    biology_doc = Document(
        page_content="Mitochondria is the powerhouse of the cell.",
        metadata={"track": "NEET", "subject": "Biology", "source": "NCERT", "document_name": "bio.pdf", "page": 120, "chapter": "Cell Structure", "chunk_index": 0},
    )
    physics_doc = Document(
        page_content="Newton's second law relates force, mass, and acceleration.",
        metadata={"track": "NEET", "subject": "Physics", "source": "NCERT", "document_name": "phys.pdf", "page": 55, "chapter": "Laws of Motion", "chunk_index": 0},
    )
    add_chunks("NEET", [biology_doc, physics_doc])

    result = retrieve(query="cell energy", track="NEET", subject="Biology", score_threshold=0.0)

    assert all(doc.metadata["subject"] == "Biology" for doc in result.documents)


def test_citation_generated_from_real_metadata_no_fabrication():
    doc = Document(
        page_content="Normalization removes redundancy in relational databases.",
        metadata={"track": "Placement", "subject": "DBMS", "source": "NPTEL", "document_name": "dbms.pdf", "page": None, "chapter": None, "chunk_index": 0},
    )
    add_chunks("Placement", [doc])

    result = retrieve(query="What is normalization?", track="Placement", subject="DBMS", score_threshold=0.0)

    assert result.sufficient
    citation = result.citations[0]
    assert citation.source == "NPTEL"
    assert citation.document_name == "dbms.pdf"
    assert citation.page is None    # never fabricated
    assert citation.chapter is None  # never fabricated


def test_insufficient_retrieval_returns_structured_empty_result():
    doc = Document(
        page_content="Mitochondria is the powerhouse of the cell.",
        metadata={"track": "NEET", "subject": "Biology", "source": "NCERT", "document_name": "bio.pdf", "page": 120, "chapter": "Cell Structure", "chunk_index": 0},
    )
    add_chunks("NEET", [doc])

    # An unreasonably high threshold guarantees nothing clears the bar,
    # simulating a query the knowledge base has no good match for.
    result = retrieve(query="What is the capital of France?", track="NEET", subject="Biology", score_threshold=0.999)

    assert result.sufficient is False
    assert result.documents == []
    assert result.citations == []


def test_basic_semantic_retrieval_matches_paraphrased_query():
    doc = Document(
        page_content="Mitochondria is the powerhouse of the cell, producing ATP through respiration.",
        metadata={"track": "NEET", "subject": "Biology", "source": "NCERT", "document_name": "bio.pdf", "page": 120, "chapter": "Cell Structure", "chunk_index": 0},
    )
    add_chunks("NEET", [doc])

    # Deliberately worded differently from the source text to confirm this
    # is semantic (embedding) similarity, not keyword overlap.
    result = retrieve(query="Which organelle generates energy for the cell?", track="NEET", subject="Biology")

    assert result.sufficient is True
    assert len(result.documents) >= 1
    assert result.documents[0].score > 0
    assert "Mitochondria" in result.documents[0].content
