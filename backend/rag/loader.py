"""
PDF document loading for the RAG knowledge base.

Loads PDFs with LangChain's PyPDFLoader, attaches the metadata every later
stage depends on (track, subject, source label, document name, page number),
and reports per-file failures instead of silently skipping bad PDFs.

Track/subject/source validation also lives here, since it is the ingestion
entry point where those values first arrive from the CLI.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

# ---------------------------------------------------------------------------
# Track / subject / source vocabulary (matches the Phase 1 architecture --
# these are not redefined anywhere else in the codebase).
# ---------------------------------------------------------------------------

TRACK_SUBJECTS: dict[str, set[str]] = {
    "NEET": {"Physics", "Chemistry", "Biology"},
    "Placement": {"Java", "SQL", "Aptitude", "DBMS", "DSA"},
}

# Source attribution labels. NCERT/NPTEL must be requested explicitly by the
# person running ingestion -- nothing here ever guesses or defaults a source.
SOURCE_LABELS: set[str] = {"NCERT", "NPTEL", "OTHER"}


def validate_track(track: str) -> None:
    if track not in TRACK_SUBJECTS:
        raise ValueError(f"Unknown track '{track}'. Valid tracks: {sorted(TRACK_SUBJECTS)}")


def validate_subject(track: str, subject: str) -> None:
    validate_track(track)
    if subject not in TRACK_SUBJECTS[track]:
        raise ValueError(
            f"Subject '{subject}' is not valid for track '{track}'. "
            f"Valid subjects for {track}: {sorted(TRACK_SUBJECTS[track])}"
        )


def validate_source(source: str) -> None:
    if source not in SOURCE_LABELS:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {sorted(SOURCE_LABELS)}")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class LoadFailure:
    file_path: str
    error: str


@dataclass
class LoadResult:
    documents: list[Document] = field(default_factory=list)   # one Document per page
    discovered_files: list[Path] = field(default_factory=list)
    processed_files: list[Path] = field(default_factory=list)
    failures: list[LoadFailure] = field(default_factory=list)

    @property
    def pages_processed(self) -> int:
        return len(self.documents)


# ---------------------------------------------------------------------------
# Loading functions
# ---------------------------------------------------------------------------

def discover_pdfs(directory: Path) -> list[Path]:
    """Find all PDF files under a directory (recursively), in a stable order."""
    return sorted(p for p in directory.rglob("*.pdf") if p.is_file())


def load_pdf(
    file_path: Path,
    *,
    track: str,
    subject: str,
    source: str,
    chapter: Optional[str] = None,
) -> tuple[list[Document], Optional[LoadFailure]]:
    """
    Load a single PDF and attach required metadata to each page.

    Returns (documents, None) on success or ([], LoadFailure) on failure --
    callers decide whether to keep going with the rest of a batch.

    `chapter` is only ever what the caller explicitly supplied (via the
    ingestion CLI's --chapter flag). It is never inferred/guessed from the
    PDF content -- guessing wrong would fabricate a citation field, which is
    an explicit guardrail for this project.
    """
    try:
        pages = PyPDFLoader(str(file_path)).load()
    except Exception as exc:  # noqa: BLE001 -- intentionally broad: any parse failure is reported, not swallowed
        return [], LoadFailure(file_path=str(file_path), error=str(exc))

    document_name = file_path.name
    enriched: list[Document] = []
    for page_doc in pages:
        page_index = page_doc.metadata.get("page")
        human_page = (page_index + 1) if isinstance(page_index, int) else None

        metadata = {
            "source": source,
            "track": track,
            "subject": subject,
            "document_name": document_name,
            "page": human_page,
            "chapter": chapter,  # None ("unknown") unless explicitly supplied
            "source_type": "pdf",
            "relative_path": str(file_path),
        }
        enriched.append(Document(page_content=page_doc.page_content, metadata=metadata))

    return enriched, None


def load_directory(
    directory: Path,
    *,
    track: str,
    subject: str,
    source: str,
    chapter: Optional[str] = None,
) -> LoadResult:
    """Load every PDF in a directory (recursively), continuing past individual failures."""
    result = LoadResult(discovered_files=discover_pdfs(directory))

    for file_path in result.discovered_files:
        documents, failure = load_pdf(file_path, track=track, subject=subject, source=source, chapter=chapter)
        if failure is not None:
            result.failures.append(failure)
            continue
        result.documents.extend(documents)
        result.processed_files.append(file_path)

    return result


def load_track_documents(
    *,
    track: str,
    subject: str,
    source: str,
    input_dir: str | Path,
    chapter: Optional[str] = None,
) -> LoadResult:
    """
    Validated entry point used by the ingestion script: checks track/subject/
    source are all legal combinations before touching the filesystem.
    """
    validate_track(track)
    validate_subject(track, subject)
    validate_source(source)

    directory = Path(input_dir)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Input directory not found: {directory}")

    return load_directory(directory, track=track, subject=subject, source=source, chapter=chapter)
