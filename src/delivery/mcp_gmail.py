import logging
from typing import Any

from mcp import ClientSession

from src import config
from src.delivery.client import MCPDeliveryError, get_mcp_client

logger = logging.getLogger(__name__)


async def create_draft(
    subject: str,
    body_html: str,
    recipient: str | None = None,
    doc_url: str | None = None,
    session: ClientSession | None = None,
) -> dict[str, Any]:
    """
    Creates an email draft in Gmail containing the Weekly Pulse HTML note
    using the MCP Server tool 'gmail_create_draft'.

    Args:
        subject: The subject line for the weekly pulse email.
        body_html: The rendered HTML email body.
        recipient: Target recipient email. If None, uses config.PULSE_RECIPIENT_EMAIL.
        doc_url: Optional link to the published Google Doc.
        session: Optional active MCP ClientSession. If None, connects automatically.

    Returns:
        Dict with keys: 'recipient', 'subject', 'status', 'doc_url', and 'result'.

    Raises:
        MCPDeliveryError: If the MCP tool invocation fails.
    """
    to_email = recipient or config.PULSE_RECIPIENT_EMAIL or ""

    # Include Google Doc link in HTML footer if provided and not present
    enriched_html = body_html
    if doc_url and doc_url not in enriched_html:
        doc_banner = (
            f'<div style="margin-top:20px;padding:12px 16px;background-color:#eff6ff;'
            f'border:1px solid #bfdbfe;border-radius:6px;font-size:13px;color:#1e40af;">'
            f'📄 <strong>Google Doc Version:</strong> <a href="{doc_url}" style="color:#2563eb;">Open Pulse Document</a>'
            f'</div>'
        )
        enriched_html = enriched_html.replace("</div>\n      </div>\n\n      <!-- Footer -->", f"{doc_banner}</div>\n      </div>\n\n      <!-- Footer -->")

    async def _execute_create_draft(active_session: ClientSession) -> dict[str, Any]:
        logger.info("Calling MCP tool 'gmail_create_draft' (to: '%s', subject: '%s')...", to_email, subject)
        tool_args: dict[str, Any] = {
            "subject": subject,
            "body_html": enriched_html,
        }
        if to_email:
            tool_args["to"] = to_email

        result = await active_session.call_tool("gmail_create_draft", arguments=tool_args)
        logger.info("✅ Gmail draft created successfully.")

        return {
            "recipient": to_email,
            "subject": subject,
            "doc_url": doc_url,
            "status": "created",
            "result": result,
        }

    if session is not None:
        return await _execute_create_draft(session)

    async with get_mcp_client() as new_session:
        return await _execute_create_draft(new_session)


async def send_email(
    subject: str,
    body_html: str,
    recipient: str,
    session: ClientSession | None = None,
) -> dict[str, Any]:
    """
    Directly sends an email via Gmail using the MCP Server tool 'gmail_send_email'.
    """
    if not recipient:
        raise MCPDeliveryError("Recipient email address is required to send an email.")

    async def _execute_send_email(active_session: ClientSession) -> dict[str, Any]:
        logger.info("Calling MCP tool 'gmail_send_email' to %s...", recipient)
        result = await active_session.call_tool(
            "gmail_send_email",
            arguments={
                "to": recipient,
                "subject": subject,
                "body_html": body_html,
            },
        )
        logger.info("✅ Email successfully sent to %s.", recipient)
        return {
            "recipient": recipient,
            "subject": subject,
            "status": "sent",
            "result": result,
        }

    if session is not None:
        return await _execute_send_email(session)

    async with get_mcp_client() as new_session:
        return await _execute_send_email(new_session)
