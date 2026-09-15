import logging
from typing import Any

from mcp import ClientSession

from src import config
from src.delivery.client import MCPDeliveryError, get_mcp_client

logger = logging.getLogger(__name__)


async def publish_to_docs(
    markdown: str,
    document_id: str | None = None,
    session: ClientSession | None = None,
) -> dict[str, Any]:
    """
    Appends the weekly pulse Markdown note to a Google Doc via the MCP Server
    using the 'gdocs_append_content' tool.

    Args:
        markdown: The rendered Markdown content of the weekly pulse.
        document_id: The Google Document ID. If None, uses config.GOOGLE_DOC_ID.
        session: Optional active MCP ClientSession. If None, connects automatically.

    Returns:
        Dict with keys: 'doc_url', 'document_id', 'status', and 'response'.

    Raises:
        MCPDeliveryError: If document_id is missing or the MCP tool call fails.
    """
    doc_id = document_id or config.GOOGLE_DOC_ID
    if not doc_id:
        raise MCPDeliveryError(
            "GOOGLE_DOC_ID is not configured. Please set GOOGLE_DOC_ID in your .env or pass document_id."
        )

    async def _execute_doc_append(active_session: ClientSession) -> dict[str, Any]:
        logger.info("Verifying Google Doc metadata for doc_id=%s via MCP...", doc_id)
        try:
            doc_info = await active_session.call_tool(
                "gdocs_get_document_info",
                arguments={"document_id": doc_id},
            )
            logger.debug("Google Doc info response: %s", doc_info)
        except Exception as exc:
            logger.warning("Could not fetch document info (proceeding with append): %s", exc)

        logger.info("Calling MCP tool 'gdocs_append_content' for doc_id=%s...", doc_id)
        result = await active_session.call_tool(
            "gdocs_append_content",
            arguments={
                "document_id": doc_id,
                "text_content": markdown,
                "insert_line_break": True,
                "formatting": "PLAIN_TEXT",
            },
        )

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        logger.info("✅ Weekly pulse successfully published to Google Doc: %s", doc_url)

        return {
            "doc_url": doc_url,
            "document_id": doc_id,
            "status": "success",
            "result": result,
        }

    if session is not None:
        return await _execute_doc_append(session)

    async with get_mcp_client() as new_session:
        return await _execute_doc_append(new_session)
