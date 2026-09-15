from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator

from mcp import ClientSession
from mcp.client.sse import sse_client

from src import config

logger = logging.getLogger(__name__)


class MCPDeliveryError(Exception):
    """Raised when an MCP delivery operation or connection fails."""
    pass


@asynccontextmanager
async def get_mcp_client(url: str | None = None) -> AsyncIterator[ClientSession]:
    """
    Async context manager establishing an MCP ClientSession over SSE transport
    with the deployed Google Tools MCP Server on Railway.
    """
    target_url = url or config.MCP_SERVER_URL
    logger.info("Connecting to MCP Server via SSE at %s...", target_url)

    try:
        async with sse_client(target_url, timeout=15.0) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logger.debug("MCP session initialized successfully.")
                yield session
    except Exception as exc:
        logger.error("MCP Server connection error on %s: %s", target_url, exc)
        raise MCPDeliveryError(f"Failed to connect to MCP server ({target_url}): {exc}") from exc
