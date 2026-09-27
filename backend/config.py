"""
Centralized application configuration.

All values are loaded from environment variables (optionally via a local .env
file). Nothing here is hardcoded as a production secret -- see .env.example
for the variables this project expects.
"""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor for resolving relative paths (e.g. CHROMA_PERSIST_DIRECTORY) so they
# work the same way regardless of the process's current working directory --
# scripts/ingest_documents.py, scripts/query_rag.py, uvicorn, and pytest can
# all be launched from different directories.
BASE_DIR = Path(__file__).resolve().parent  # backend/


class Settings(BaseSettings):
    # General
    APP_NAME: str = "Adaptive AI Study Tutor API"

    # Database
    DATABASE_URL: str = "sqlite:///./app.db"

    # JWT authentication (JWT_SECRET_KEY has no default on purpose -- it must
    # come from the environment / .env file, never be hardcoded in source).
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Adaptive-learning tuning knobs (used by later phases, wired here so the
    # rest of the system can rely on a single configuration source from day one).
    MASTERY_THRESHOLD_PERCENT: float = 60
    REACT_MAX_ITERATIONS: int = 3
    ADAPTIVE_MAX_RETRIES: int = 2

    # RAG pipeline (Phase 3)
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    CHROMA_PERSIST_DIRECTORY: str = "../data/chroma"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    RAG_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.35

    # LLM provider (Phase 5/6). No default key -- must come from the
    # environment. Optional[None] so the app can still start (e.g. to run
    # Phase 2/3 tests) without one configured; code paths that actually need
    # the LLM raise a clear error if it's missing rather than failing obscurely.
    GROQ_API_KEY: Optional[str] = None
    # Verified against this project's real Groq account (Sept 2026): the
    # classic "llama-3.3-70b-versatile" name is not available on this
    # account (404 model_not_found) -- Groq's catalog has shifted since.
    # openai/gpt-oss-120b was confirmed to produce valid, well-grounded
    # quiz JSON and explanations against a real call; openai/gpt-oss-20b is
    # a faster/cheaper alternative if latency matters more than the small
    # quality edge observed. Always confirm current availability with
    # `client.models.list()` against your own key before deploying.
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # Web search fallback (Phase 6). Same optional-key pattern as Groq above.
    TAVILY_API_KEY: Optional[str] = None

    # CORS (Phase 8) -- comma-separated origins allowed to call the API from
    # a browser. Defaults to Vite's dev server port only; never a wildcard,
    # since credentials (the Authorization header) are allowed.
    CORS_ORIGINS: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        # Anchored to backend/.env explicitly (not a bare relative ".env")
        # so it is found regardless of the process's current working
        # directory -- e.g. scripts/ingest_documents.py is documented to be
        # run from the project root, not from backend/.
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def chroma_persist_path(self) -> Path:
        """
        Absolute, CWD-independent path to the Chroma persistence directory.
        A relative CHROMA_PERSIST_DIRECTORY is resolved against backend/
        (this file's directory), not against wherever the process happened
        to be launched from.
        """
        path = Path(self.CHROMA_PERSIST_DIRECTORY)
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        return path

    @property
    def sqlite_file_path(self) -> Path:
        """
        Absolute, CWD-independent path to the SQLite file behind
        DATABASE_URL. Both database/database.py's SQLAlchemy engine and
        graph/workflow.py's LangGraph checkpointer are built from this same
        property specifically so they are guaranteed to open the exact same
        file (the architecture requires "the SAME SQLite database file") --
        a bare "sqlite:///./app.db" would otherwise resolve relative to
        whatever the process's current working directory happens to be.
        """
        if not self.DATABASE_URL.startswith("sqlite"):
            raise ValueError("sqlite_file_path is only valid for a sqlite:// DATABASE_URL")
        raw_path = self.DATABASE_URL.split("///", 1)[1]
        path = Path(raw_path)
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        return path

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
