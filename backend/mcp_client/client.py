"""
MCP client (Phase 4): the only path agents use to reach the MCP server's tools.

Uses stdio transport: a single long-lived subprocess + ClientSession, reused
across every tool call for the lifetime of the FastAPI process (see
main.py's lifespan), rather than spawning a fresh subprocess per call --
generate_quiz's first RAG lookup loads the HuggingFace embedding model,
which costs ~20-30s cold; that cost must be paid once per process, not once
per request.

Important, easy-to-miss detail: mcp.client.stdio.stdio_client only forwards
a curated "safe" subset of the parent's environment to the subprocess by
default (PATH, HOME, etc.) -- NOT this project's own config (DATABASE_URL,
JWT_SECRET_KEY, GROQ_API_KEY, ...). Without explicitly passing `env=os.environ`
below, the MCP server subprocess's own `config.py` would fail at import time
(JWT_SECRET_KEY has no default) or silently point at the wrong database.
"""
import asyncio
import json
import logging
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"
BACKEND_DIR = SERVER_SCRIPT.parent.parent


class MCPToolError(RuntimeError):
    """Raised when the MCP server reports a tool failure (is_error=True)."""


class MCPClient:
    """A long-lived MCP client session. Call connect() once, call_tool() many times, close() once."""

    def __init__(self) -> None:
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Start the MCP server subprocess and establish a session (idempotent -- safe to call repeatedly)."""
        if self._session is not None:
            return

        params = StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER_SCRIPT)],
            cwd=str(BACKEND_DIR),
            env=dict(os.environ),  # see module docstring -- required, not optional
        )
        exit_stack = AsyncExitStack()
        try:
            read, write = await exit_stack.enter_async_context(stdio_client(params))
            session = await exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception:
            await exit_stack.aclose()
            raise

        self._exit_stack = exit_stack
        self._session = session
        logger.info("MCP client connected to server subprocess (%s)", SERVER_SCRIPT)

    async def close(self) -> None:
        """Shut down the subprocess and clear session state. Safe to call even if never connected."""
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._session = None
        self._exit_stack = None

    async def list_tool_names(self) -> list[str]:
        await self.connect()
        assert self._session is not None
        result = await self._session.list_tools()
        return [t.name for t in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict:
        """
        Calls one MCP tool and returns its parsed JSON result.

        Raises MCPToolError for any tool-side failure (anticipated or not --
        the server's ToolError/UnexpectedToolError distinction only affects
        how much detail is in the message and whether it's logged with a
        traceback server-side; this client surfaces whatever message came back).
        """
        await self.connect()
        assert self._session is not None

        async with self._lock:  # serialize calls through the single stdio session
            try:
                result = await self._session.call_tool(name, arguments)
            except Exception as exc:
                raise MCPToolError(f"MCP transport error calling '{name}': {exc}") from exc

        if result.is_error:
            message = result.content[0].text if result.content else f"MCP tool '{name}' failed with no detail"
            raise MCPToolError(message)

        if not result.content:
            return {}
        return json.loads(result.content[0].text)


_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Process-wide singleton -- see module docstring for why this must be reused, not recreated per call."""
    global _client
    if _client is None:
        _client = MCPClient()
    return _client


async def reset_mcp_client() -> None:
    """Closes and drops the singleton. Used by tests to get an isolated subprocess+session per test."""
    global _client
    if _client is not None:
        await _client.close()
    _client = None
