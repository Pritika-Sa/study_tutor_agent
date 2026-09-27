"""
Test-session setup.

Three jobs:
1. Put the backend/ directory on sys.path so `import main`, `import config`,
   etc. resolve the same way they do when running `uvicorn main:app` from
   inside backend/.
2. Force the app to use an isolated SQLite file (test_app.db) instead of the
   real app.db.
3. Clean that test database up before and after the run.

The pre-run cleanup happens here, at module import time, because pytest
imports conftest.py before it imports any test module -- and importing
test_auth.py is what triggers `from main import app`, which opens the
SQLite connection pool. On Windows, an open sqlite3 file handle cannot be
deleted, so the file must be removed *before* that import happens, not
inside a fixture that runs afterwards.
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_DB_PATH = BACKEND_DIR / "test_app.db"

# Explicit os.environ assignment (not setdefault) so these values win even if
# a real backend/.env exists on disk -- tests never touch production config.
os.environ["JWT_SECRET_KEY"] = "test-only-secret-never-use-in-production"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["MASTERY_THRESHOLD_PERCENT"] = "60"
os.environ["REACT_MAX_ITERATIONS"] = "3"
os.environ["ADAPTIVE_MAX_RETRIES"] = "2"

if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_test_database():
    yield
    # Release SQLAlchemy's pooled connections before removing the file --
    # required on Windows, where an open handle blocks deletion.
    from database.database import engine

    engine.dispose()
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except PermissionError:
            pass  # best-effort cleanup only; does not affect test results
