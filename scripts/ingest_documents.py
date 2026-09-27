#!/usr/bin/env python
"""
CLI: ingest PDF documents into the track-specific ChromaDB collection.

Example:
    python scripts/ingest_documents.py \\
        --track NEET --subject Biology --source NCERT --input data/neet/biology/

    python scripts/ingest_documents.py \\
        --track Placement --subject DBMS --source NPTEL --input data/placement/dbms/ \\
        --chapter Normalization
"""
import argparse
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag.loader import SOURCE_LABELS, TRACK_SUBJECTS, load_track_documents  # noqa: E402
from rag.splitter import split_documents  # noqa: E402
from rag.vectorstore import add_chunks  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest PDF documents into the Adaptive AI Study Tutor knowledge base.")
    parser.add_argument("--track", required=True, choices=sorted(TRACK_SUBJECTS.keys()))
    parser.add_argument("--subject", required=True, help="Must be a valid subject for the given track")
    parser.add_argument("--source", required=True, choices=sorted(SOURCE_LABELS), help="Where this material actually came from -- never guessed")
    parser.add_argument("--input", required=True, help="Directory containing PDF files to ingest (searched recursively)")
    parser.add_argument("--chapter", default=None, help="Optional chapter/topic label applied to every PDF in this run")
    parser.add_argument("--chunk-size", type=int, default=None, help="Overrides CHUNK_SIZE from config for this run")
    parser.add_argument("--chunk-overlap", type=int, default=None, help="Overrides CHUNK_OVERLAP from config for this run")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started_at = time.time()

    try:
        load_result = load_track_documents(
            track=args.track,
            subject=args.subject,
            source=args.source,
            input_dir=args.input,
            chapter=args.chapter,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Ingestion aborted: {exc}")
        sys.exit(1)

    if load_result.failures:
        print("The following files could not be parsed and were skipped:")
        for failure in load_result.failures:
            print(f"  - {failure.file_path}: {failure.error}")
        print()

    if not load_result.documents:
        print("No pages were successfully extracted -- nothing to chunk or store.")
        chunks = []
        outcome = add_chunks(args.track, [])
    else:
        chunks = split_documents(load_result.documents, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
        outcome = add_chunks(args.track, chunks)

    elapsed = time.time() - started_at

    print("=" * 50)
    print("RAG INGESTION COMPLETE")
    print("=" * 50)
    print(f"Track: {args.track}")
    print(f"Subject: {args.subject}")
    print(f"Source: {args.source}")
    print()
    print(f"Documents discovered: {len(load_result.discovered_files)}")
    print(f"Documents processed: {len(load_result.processed_files)}")
    print(f"Pages processed: {load_result.pages_processed}")
    print(f"Chunks created: {len(chunks)}")
    print(f"Chunks inserted: {outcome.inserted}")
    print(f"Duplicates skipped: {outcome.duplicates_skipped}")
    print(f"Failures: {len(load_result.failures)}")
    print()
    print(f"Collection: {outcome.collection}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print("=" * 50)


if __name__ == "__main__":
    main()
