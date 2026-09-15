import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from src.delivery import (
    MCPDeliveryError,
    create_draft,
    get_mcp_client,
    publish_to_docs,
    send_email,
)


def test_publish_to_docs_mocked():
    """Verify publish_to_docs calls gdocs_append_content on the MCP session."""
    async def _run():
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value={"status": "appended"})

        markdown_text = "# Test Markdown Pulse"
        doc_id = "test-doc-id-123"

        result = await publish_to_docs(
            markdown=markdown_text,
            document_id=doc_id,
            session=mock_session,
        )

        assert result["status"] == "success"
        assert result["document_id"] == doc_id
        assert f"https://docs.google.com/document/d/{doc_id}/edit" in result["doc_url"]

        # Verify tool call args
        mock_session.call_tool.assert_any_call(
            "gdocs_append_content",
            arguments={
                "document_id": doc_id,
                "text_content": markdown_text,
                "insert_line_break": True,
                "formatting": "PLAIN_TEXT",
            },
        )

    asyncio.run(_run())


def test_publish_to_docs_missing_doc_id():
    """Verify publish_to_docs raises MCPDeliveryError when document_id is not set."""
    async def _run():
        with patch("src.config.GOOGLE_DOC_ID", None):
            with pytest.raises(MCPDeliveryError, match="GOOGLE_DOC_ID is not configured"):
                await publish_to_docs(markdown="# Test", document_id=None)

    asyncio.run(_run())


def test_create_draft_mocked():
    """Verify create_draft calls gmail_create_draft on the MCP session."""
    async def _run():
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value={"id": "draft-abc-123"})

        html_content = "<p>Test Pulse HTML</p>"
        recipient = "pm@example.com"
        subject = "📊 Test Pulse"
        doc_url = "https://docs.google.com/document/d/123/edit"

        result = await create_draft(
            subject=subject,
            body_html=html_content,
            recipient=recipient,
            doc_url=doc_url,
            session=mock_session,
        )

        assert result["status"] == "created"
        assert result["recipient"] == recipient
        assert result["subject"] == subject

        mock_session.call_tool.assert_called_once()
        called_args = mock_session.call_tool.call_args[1]["arguments"]
        assert called_args["to"] == recipient
        assert called_args["subject"] == subject
        assert "Test Pulse HTML" in called_args["body_html"]

    asyncio.run(_run())


def test_send_email_mocked():
    """Verify send_email calls gmail_send_email on the MCP session."""
    async def _run():
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value={"id": "msg-xyz-999"})

        result = await send_email(
            subject="Test Subject",
            body_html="<p>Test</p>",
            recipient="eng@example.com",
            session=mock_session,
        )

        assert result["status"] == "sent"
        assert result["recipient"] == "eng@example.com"
        mock_session.call_tool.assert_called_once_with(
            "gmail_send_email",
            arguments={
                "to": "eng@example.com",
                "subject": "Test Subject",
                "body_html": "<p>Test</p>",
            },
        )

    asyncio.run(_run())


def test_live_railway_mcp_server_tools_discovery():
    """Verify live connection to Railway MCP server discovers Google Docs and Gmail tools."""
    async def _run():
        try:
            async with get_mcp_client() as session:
                tools_response = await session.list_tools()
                tool_names = {t.name for t in tools_response.tools}
                expected_tools = {
                    "gmail_send_email",
                    "gmail_create_draft",
                    "gdocs_append_content",
                    "gdocs_get_document_info",
                }
                assert expected_tools.issubset(tool_names), f"Missing tools in {tool_names}"
        except MCPDeliveryError:
            pytest.skip("Railway MCP server endpoint temporarily unreachable from current network.")

    asyncio.run(_run())

