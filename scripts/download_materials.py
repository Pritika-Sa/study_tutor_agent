#!/usr/bin/env python
"""
CLI: download official/open-educational study material PDFs into the correct
data/<track>/<subject>/ directory, then (optionally) run the existing
ingestion pipeline on them.

This script is responsible ONLY for obtaining and organizing source
documents. It never re-implements PDF loading, chunking, embedding, or
Chroma insertion -- scripts/ingest_documents.py (unchanged) still owns all
of that.

Source policy (see MATERIALS / NCERT_SOURCES / PLACEMENT_SOURCES below):
  - NEET (Physics, Chemistry, Biology): official NCERT textbook PDFs only,
    served directly from ncert.nic.in as "complete book" ZIP bundles of
    per-chapter PDFs. Every URL below was verified by this project (HTTP 200,
    correct content type, correct magic bytes) before being hardcoded --
    never guessed.
  - Placement: Java, DSA, DBMS, SQL each map to a verified, legitimately
    openly-licensed textbook/reference PDF (see each entry's `publisher` /
    `license` fields). None of these are actually NPTEL material, so they
    are ingested with --source OTHER, which is the accurate existing label
    for "real material, not NCERT/NPTEL" in rag/loader.py's SOURCE_LABELS.
    Aptitude has NO configured source: no NPTEL PDF and no legitimately
    licensed open textbook could be verified for it. It is intentionally
    left empty rather than guessed or mislabeled -- see --list output and
    the final summary for how this is reported.

Examples:
    python scripts/download_materials.py --list
    python scripts/download_materials.py --track NEET --subject Biology
    python scripts/download_materials.py --track NEET
    python scripts/download_materials.py --all
    python scripts/download_materials.py --all --force --ingest
"""
import argparse
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DIR = (DATA_DIR / "chroma").resolve()

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag.loader import TRACK_SUBJECTS  # noqa: E402 -- reuse the real vocabulary, never redefine it

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MIN_VALID_PDF_BYTES = 5_000     # reject tiny error pages masquerading as PDFs
MIN_VALID_ZIP_BYTES = 50_000    # reject tiny error pages masquerading as ZIPs
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 4
DOWNLOAD_TIMEOUT_SECONDS = 60

TRACK_DIR_NAMES = {"NEET": "neet", "Placement": "placement"}

NCERT_BASE = "https://ncert.nic.in/textbook/pdf"

# ---------------------------------------------------------------------------
# Source configuration. Every URL here was independently verified (HTTP 200,
# real magic bytes, real file size) against the live official/open source
# before being hardcoded -- see the ingestion report for the verification
# transcript. Nothing here is guessed.
# ---------------------------------------------------------------------------

NCERT_SOURCES: dict[str, list[dict]] = {
    "Physics": [
        {"title": "Physics Part I", "class": "XI", "code": "keph1", "url": f"{NCERT_BASE}/keph1dd.zip"},
        {"title": "Physics Part II", "class": "XI", "code": "keph2", "url": f"{NCERT_BASE}/keph2dd.zip"},
        {"title": "Physics Part I", "class": "XII", "code": "leph1", "url": f"{NCERT_BASE}/leph1dd.zip"},
        {"title": "Physics Part II", "class": "XII", "code": "leph2", "url": f"{NCERT_BASE}/leph2dd.zip"},
    ],
    "Chemistry": [
        {"title": "Chemistry Part I", "class": "XI", "code": "kech1", "url": f"{NCERT_BASE}/kech1dd.zip"},
        {"title": "Chemistry Part II", "class": "XI", "code": "kech2", "url": f"{NCERT_BASE}/kech2dd.zip"},
        {"title": "Chemistry Part I", "class": "XII", "code": "lech1", "url": f"{NCERT_BASE}/lech1dd.zip"},
        {"title": "Chemistry Part II", "class": "XII", "code": "lech2", "url": f"{NCERT_BASE}/lech2dd.zip"},
    ],
    "Biology": [
        {"title": "Biology", "class": "XI", "code": "kebo1", "url": f"{NCERT_BASE}/kebo1dd.zip"},
        {"title": "Biology", "class": "XII", "code": "lebo1", "url": f"{NCERT_BASE}/lebo1dd.zip"},
    ],
}

# Placement sources: none of these are NPTEL. Each is a verified,
# legitimately openly-licensed textbook/reference. `source` is the label the
# existing ingestion pipeline accepts (rag/loader.py SOURCE_LABELS =
# {"NCERT", "NPTEL", "OTHER"}); `publisher`/`license` record the real,
# accurate attribution for reporting even though the pipeline's own metadata
# schema doesn't have a dedicated field for it.
PLACEMENT_SOURCES: dict[str, list[dict]] = {
    "Java": [
        {
            "title": "Think Java, 2nd Edition",
            "source": "OTHER",
            "publisher": "Allen B. Downey & Chris Mayfield / Green Tea Press",
            "license": "CC BY-NC-SA",
            "url": "https://greenteapress.com/thinkjava7/thinkjava2.pdf",
            "filename": "think_java_2e.pdf",
        },
    ],
    "DSA": [
        {
            "title": "Open Data Structures (in Java), Edition 0.1G",
            "source": "OTHER",
            "publisher": "Pat Morin / Athabasca University Press",
            "license": "CC BY",
            "url": "https://opendatastructures.org/ods-java.pdf",
            "filename": "open_data_structures_java.pdf",
        },
    ],
    "DBMS": [
        {
            "title": "Database Design, 2nd Edition",
            "source": "OTHER",
            "publisher": "Adrienne Watt & Nelson Eng / BCcampus Open Textbook Project",
            "license": "CC BY 4.0",
            "url": "https://opentextbc.ca/dbdesign01/open/download?type=pdf",
            "referer": "https://opentextbc.ca/dbdesign01/",
            "filename": "database_design_2e.pdf",
        },
    ],
    "SQL": [
        {
            "title": "SQL Notes for Professionals",
            "source": "OTHER",
            "publisher": "GoalKicker.com (compiled from Stack Overflow Documentation)",
            "license": "CC BY-SA",
            "url": "https://books.goalkicker.com/SQLBook/SQLNotesForProfessionals.pdf",
            "filename": "sql_notes_for_professionals.pdf",
        },
    ],
    # Aptitude: intentionally empty. No NPTEL course offers a downloadable
    # PDF suited to this subject, and no legitimately-licensed open
    # educational "quantitative aptitude" textbook could be verified during
    # research for this script. Forcing a source here would violate the
    # "never fabricate/mislabel a source" rule -- see the final report for
    # exact next steps a human can take instead.
    "Aptitude": [],
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SubjectResult:
    track: str
    subject: str
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    unavailable: bool = False  # no configured source at all (e.g. Aptitude)
    failure_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Networking / validation helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9._-]", "", name) or "download.pdf"


def _fetch(url: str, referer: Optional[str] = None) -> bytes:
    """Stream a URL into memory with a browser-like User-Agent (some official
    hosts, e.g. Cloudflare-fronted Pressbooks sites, reject bare urllib
    requests) and a real timeout. Raises on any HTTP/network error."""
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise urllib.error.HTTPError(url, status, "Non-200 status", response.headers, None)
        chunks = []
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)


def _looks_like_html(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _validate_pdf(data: bytes) -> Optional[str]:
    """Returns an error string if invalid, else None."""
    if len(data) < MIN_VALID_PDF_BYTES:
        return f"file too small ({len(data)} bytes) to be a real PDF"
    if _looks_like_html(data):
        return "downloaded content is an HTML page, not a PDF"
    if not data[:5] == b"%PDF-":
        return "downloaded content does not start with the PDF magic bytes (%PDF-)"
    return None


def _validate_zip(data: bytes) -> Optional[str]:
    if len(data) < MIN_VALID_ZIP_BYTES:
        return f"file too small ({len(data)} bytes) to be a real ZIP bundle"
    if _looks_like_html(data):
        return "downloaded content is an HTML page, not a ZIP"
    if not data[:4] == b"PK\x03\x04":
        return "downloaded content does not start with the ZIP magic bytes (PK..)"
    return None


def _download_with_retries(url: str, referer: Optional[str], validator) -> tuple[Optional[bytes], Optional[str]]:
    """Returns (data, None) on success or (None, error_message) after all retries fail."""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = _fetch(url, referer=referer)
        except Exception as exc:  # noqa: BLE001 -- any network failure is reported, not swallowed
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            error = validator(data)
            if error is None:
                return data, None
            last_error = error
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS * attempt)
    return None, last_error


# ---------------------------------------------------------------------------
# Per-subject download logic
# ---------------------------------------------------------------------------

def _subject_dir(track: str, subject: str) -> Path:
    directory = DATA_DIR / TRACK_DIR_NAMES[track] / subject.lower()
    resolved = directory.resolve()
    if resolved == CHROMA_DIR or CHROMA_DIR in resolved.parents:
        raise RuntimeError(f"Refusing to download into the Chroma directory: {resolved}")
    return directory


def download_ncert_entry(subject: str, entry: dict, dest_dir: Path, force: bool) -> tuple[str, list[str]]:
    """Returns (status, messages). status in {"downloaded", "skipped", "failed"}."""
    code = entry["code"]
    label = f'NCERT {entry["title"]} (Class {entry["class"]})'
    existing = sorted(dest_dir.glob(f"{code}*.pdf"))
    if existing and not force:
        return "skipped", [f"  Already exists -- skipping: {label} ({len(existing)} chapter PDFs present)"]

    messages = [f"  Downloading: {label}"]
    data, error = _download_with_retries(entry["url"], referer=None, validator=_validate_zip)
    if error is not None:
        messages.append(f"  FAILED -- {label}: {error}")
        return "failed", messages

    import io
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            pdf_names = [n for n in archive.namelist() if n.lower().endswith(".pdf")]
            if not pdf_names:
                messages.append(f"  FAILED -- {label}: ZIP contained no PDF files")
                return "failed", messages
            dest_dir.mkdir(parents=True, exist_ok=True)
            for name in pdf_names:
                # Flatten: NCERT ZIPs are flat already, but never trust a
                # path from inside an archive -- use the basename only.
                out_path = dest_dir / Path(name).name
                with archive.open(name) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())
    except zipfile.BadZipFile as exc:
        messages.append(f"  FAILED -- {label}: corrupt ZIP ({exc})")
        return "failed", messages

    messages.append(f"  Downloaded successfully: {label} ({len(pdf_names)} chapter PDFs)")
    return "downloaded", messages


def download_placement_entry(subject: str, entry: dict, dest_dir: Path, force: bool) -> tuple[str, list[str]]:
    filename = _sanitize_filename(entry["filename"])
    dest_path = dest_dir / filename
    label = f'{entry["source"]}-labelled material: "{entry["title"]}" ({entry["publisher"]}, {entry["license"]})'

    if dest_path.exists() and not force:
        return "skipped", [f"  Already exists -- skipping: {label}"]

    messages = [f"  Downloading: {label}"]
    data, error = _download_with_retries(entry["url"], referer=entry.get("referer"), validator=_validate_pdf)
    if error is not None:
        messages.append(f"  FAILED -- {label}: {error}")
        return "failed", messages

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
    tmp_path.write_bytes(data)
    tmp_path.replace(dest_path)

    messages.append(f"  Downloaded successfully: {label}")
    return "downloaded", messages


def download_subject(track: str, subject: str, force: bool) -> SubjectResult:
    result = SubjectResult(track=track, subject=subject)
    dest_dir = _subject_dir(track, subject)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if track == "NEET":
        entries = NCERT_SOURCES.get(subject, [])
    else:
        entries = PLACEMENT_SOURCES.get(subject, [])

    print(f"\n[{track} / {subject}] -> {dest_dir}")
    if not entries:
        result.unavailable = True
        print("  No verified official/open-educational source is configured for this subject yet.")
        print("  Nothing downloaded -- see the final report for next steps.")
        return result

    for entry in entries:
        if track == "NEET":
            status, messages = download_ncert_entry(subject, entry, dest_dir, force)
        else:
            status, messages = download_placement_entry(subject, entry, dest_dir, force)

        for message in messages:
            print(message)

        if status == "downloaded":
            result.downloaded += 1
        elif status == "skipped":
            result.skipped += 1
        else:
            result.failed += 1
            result.failure_reasons.append(messages[-1])

    return result


# ---------------------------------------------------------------------------
# Ingestion integration (delegates entirely to the existing script)
# ---------------------------------------------------------------------------

def run_ingestion(track: str, subject: str, source: str) -> tuple[bool, str]:
    dest_dir = _subject_dir(track, subject)
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "ingest_documents.py"),
        "--track", track,
        "--subject", subject,
        "--source", source,
        "--input", str(dest_dir),
    ]
    print(f"\n[{track} / {subject}] Running: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if completed.returncode != 0:
        return False, f"ingest_documents.py exited with code {completed.returncode}"
    return True, "ok"


# ---------------------------------------------------------------------------
# --list
# ---------------------------------------------------------------------------

def print_material_list() -> None:
    header = f'{"Track":<11}{"Subject":<11}{"Title":<32}{"Source":<10}{"Destination"}'
    print(header)
    print("-" * len(header))
    for subject, entries in NCERT_SOURCES.items():
        for entry in entries:
            dest = _subject_dir("NEET", subject)
            print(f'{"NEET":<11}{subject:<11}{entry["title"] + " (Cl. " + entry["class"] + ")":<32}{"NCERT":<10}{dest}')
            print(f'  URL: {entry["url"]}')
    for subject, entries in PLACEMENT_SOURCES.items():
        if not entries:
            dest = _subject_dir("Placement", subject)
            print(f'{"Placement":<11}{subject:<11}{"(none configured)":<32}{"--":<10}{dest}')
            continue
        for entry in entries:
            dest = _subject_dir("Placement", subject)
            print(f'{"Placement":<11}{subject:<11}{entry["title"]:<32}{entry["source"]:<10}{dest}')
            print(f'  URL: {entry["url"]}')
            print(f'  Actual publisher: {entry["publisher"]} ({entry["license"]})')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download official/open-educational study material PDFs and (optionally) ingest them."
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--track", choices=sorted(TRACK_SUBJECTS.keys()), help="Download material for one track")
    group.add_argument("--all", action="store_true", help="Download material for every track/subject")
    parser.add_argument("--subject", default=None, help="Restrict to one subject within --track")
    parser.add_argument("--force", action="store_true", help="Re-download even if a valid file already exists")
    parser.add_argument("--ingest", action="store_true", help="Run scripts/ingest_documents.py after downloading")
    parser.add_argument("--list", action="store_true", help="List configured materials and exit without downloading")
    return parser.parse_args()


def resolve_targets(args: argparse.Namespace) -> list[tuple[str, str]]:
    if args.subject and not args.track:
        print("Error: --subject requires --track")
        sys.exit(2)

    if args.all:
        return [(track, subject) for track in TRACK_SUBJECTS for subject in sorted(TRACK_SUBJECTS[track])]

    if args.track:
        if args.subject:
            if args.subject not in TRACK_SUBJECTS[args.track]:
                print(f"Error: '{args.subject}' is not a valid subject for {args.track}. "
                      f"Valid subjects: {sorted(TRACK_SUBJECTS[args.track])}")
                sys.exit(2)
            return [(args.track, args.subject)]
        return [(args.track, subject) for subject in sorted(TRACK_SUBJECTS[args.track])]

    print("Error: specify --track, --all, or --list")
    sys.exit(2)


def main() -> None:
    args = parse_args()

    if args.list:
        print_material_list()
        return

    targets = resolve_targets(args)

    results: list[SubjectResult] = []
    for track, subject in targets:
        results.append(download_subject(track, subject, args.force))

    print("\n" + "=" * 50)
    print("MATERIAL DOWNLOAD SUMMARY")
    print("=" * 50)
    for track in TRACK_SUBJECTS:
        track_results = [r for r in results if r.track == track]
        if not track_results:
            continue
        print(f"\n{track}")
        for r in track_results:
            if r.unavailable:
                print(f"  {r.subject:<10}: NO SOURCE CONFIGURED (skipped)")
            else:
                print(f"  {r.subject:<10}: {r.downloaded} downloaded / {r.skipped} skipped / {r.failed} failed")
    print("\n" + "=" * 50)

    any_hard_failure = any(r.failed > 0 for r in results)

    ingestion_summaries: list[str] = []
    if args.ingest:
        print("\nINGESTION")
        print("=" * 50)
        for r in results:
            if r.unavailable:
                ingestion_summaries.append(f"{r.subject:<10}: skipped (no source material)")
                continue
            if r.failed > 0 and r.downloaded == 0 and r.skipped == 0:
                ingestion_summaries.append(f"{r.subject:<10}: skipped (all downloads failed)")
                continue
            source_label = "NCERT" if r.track == "NEET" else "OTHER"
            ok, message = run_ingestion(r.track, r.subject, source_label)
            ingestion_summaries.append(f"{r.subject:<10}: {'ok' if ok else 'FAILED -- ' + message}")
            if not ok:
                any_hard_failure = True

        print("\n" + "=" * 50)
        print("INGESTION SUMMARY")
        print("=" * 50)
        for line in ingestion_summaries:
            print(line)
        print("=" * 50)

    unavailable = [r for r in results if r.unavailable]
    if unavailable:
        print("\nSources that could not be configured/downloaded (not fabricated, not attempted):")
        for r in unavailable:
            print(f"  - {r.track}/{r.subject}: no verified official/open-educational PDF found.")
            print(f"    Next step: manually source a legitimately licensed textbook/notes PDF for "
                  f"{r.subject}, place it under {_subject_dir(r.track, r.subject)}, then run:")
            print(f"    python scripts/ingest_documents.py --track {r.track} --subject {r.subject} "
                  f"--source OTHER --input {_subject_dir(r.track, r.subject)}")

    hard_failures = [r for r in results if r.failed > 0]
    if hard_failures:
        print("\nFailed downloads (not silently ignored):")
        for r in hard_failures:
            for reason in r.failure_reasons:
                print(f"  - {r.track}/{r.subject}: {reason}")

    sys.exit(1 if any_hard_failure else 0)


if __name__ == "__main__":
    main()
