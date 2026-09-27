"""
FastAPI application entry point.

Run with (from inside backend/):
    uvicorn main:app --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes_auth import router as auth_router
from api.routes_progress import router as progress_router
from api.routes_quiz import router as quiz_router
from api.routes_tutor import router as tutor_router
from config import settings
from database.schema import create_tables
from graph.workflow import get_graph_app
from mcp_client.client import get_mcp_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensures app.db and all tables exist before the first request.
    create_tables()

    # Long-lived MCP client (spawns the MCP server subprocess once, reused
    # for every request) and long-lived LangGraph checkpointer connection --
    # both documented in mcp_client/client.py and graph/workflow.py as
    # needing to persist for the app's whole lifetime, not per-request.
    await get_mcp_client().connect()
    await get_graph_app().start()
    logger.info("MCP client connected and LangGraph app started.")

    yield

    await get_graph_app().stop()
    await get_mcp_client().close()
    logger.info("LangGraph app stopped and MCP client closed.")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# CORS: origins are configurable (settings.CORS_ORIGINS, comma-separated),
# defaulting to the Vite dev server only -- never a wildcard, since
# allow_credentials=True is required for the frontend's Authorization header.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(tutor_router)
app.include_router(quiz_router)
app.include_router(progress_router)


@app.get("/")
def root() -> dict:
    return {"message": "Adaptive AI Study Tutor API", "status": "running"}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}
