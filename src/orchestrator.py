#!/usr/bin/env python3
"""
Weekly App Review Pulse — End-to-End Orchestrator.

Orchestrates all 5 phases:
1. Reviews Ingestion (Google Play Store)
2. AI Agent Analysis (Theme clustering, verbatim quotes, action items)
3. Pulse Generation (Markdown + HTML email notes)
4. MCP Delivery (Google Docs update + Gmail draft creation via Railway MCP server)
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add workspace root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src import config
from src.agent import run_analysis
from src.delivery import MCPDeliveryError, create_draft, get_mcp_client, publish_to_docs
from src.pulse import generate_pulse
from src.scraper import load_reviews

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")


async def run_pipeline(
    force_refresh_reviews: bool = False,
    deliver_mcp: bool = True,
    target_doc_id: str | None = None,
    recipient_email: str | None = None,
) -> dict:
    print("=" * 75)
    print(" 🚀 WEEKLY APP REVIEW PULSE — FULL MCP AGENT PIPELINE")
    print("=" * 75)

    # -------------------------------------------------------------
    # Step 1: Phase 2 — Review Ingestion
    # -------------------------------------------------------------
    print("\n📦 [1/4] Scraping & Ingesting Reviews...")
    print(f"   App ID: {config.TARGET_APP_ID} | Lookback: {config.REVIEW_WINDOW_WEEKS} weeks")
    reviews = load_reviews(force_refresh=force_refresh_reviews)
    print(f"   ✅ Ingested {len(reviews)} reviews.")

    if not reviews:
        print("   ⚠️ No reviews found to process.")
        return {}

    # -------------------------------------------------------------
    # Step 2: Phase 3 — LangChain AI Agent Analysis
    # -------------------------------------------------------------
    print("\n🤖 [2/4] Running AI Agent Review Analysis...")
    analysis_output = run_analysis(reviews)
    themes = analysis_output.get("themes", [])
    quotes = analysis_output.get("quotes", [])
    actions = analysis_output.get("actions", [])
    print(f"   ✅ Identified {len(themes)} themes, {len(quotes)} quotes, {len(actions)} actions.")

    # -------------------------------------------------------------
    # Step 3: Phase 4 — Pulse Generation
    # -------------------------------------------------------------
    print("\n📝 [3/4] Generating Weekly Pulse Notes (Markdown + HTML)...")
    pulse = generate_pulse(analysis_output, reviews)
    report_md = pulse["markdown"]
    report_html = pulse["html"]

    # Save outputs to data/
    md_file = ROOT_DIR / "data" / "weekly_pulse.md"
    html_file = ROOT_DIR / "data" / "weekly_pulse.html"
    md_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.write_text(report_md, encoding="utf-8")
    html_file.write_text(report_html, encoding="utf-8")
    print(f"   💾 Saved local Markdown: {md_file}")
    print(f"   💾 Saved local HTML    : {html_file}")

    # -------------------------------------------------------------
    # Step 4: Phase 5 — MCP Delivery (Google Docs + Gmail)
    # -------------------------------------------------------------
    delivery_results = {}
    if deliver_mcp:
        print("\n📤 [4/4] Delivering via MCP Server...")
        print(f"   Server URL: {config.MCP_SERVER_URL}")

        try:
            async with get_mcp_client() as mcp_session:
                doc_id = target_doc_id or config.GOOGLE_DOC_ID
                doc_url = None

                # 4a. Google Docs delivery
                if doc_id:
                    print(f"   Publishing to Google Doc (ID: {doc_id})...")
                    try:
                        doc_res = await publish_to_docs(
                            markdown=report_md,
                            document_id=doc_id,
                            session=mcp_session,
                        )
                        doc_url = doc_res.get("doc_url")
                        delivery_results["docs"] = doc_res
                        print(f"   ✅ Google Doc updated: {doc_url}")
                    except Exception as doc_err:
                        logger.warning("Failed to publish to Google Doc: %s", doc_err)
                        delivery_results["docs_error"] = str(doc_err)
                else:
                    print("   ℹ️ GOOGLE_DOC_ID not configured in .env (skipping Doc update).")

                # 4b. Gmail draft delivery
                to_email = recipient_email or config.PULSE_RECIPIENT_EMAIL
                print(f"   Creating Gmail draft (Recipient: {to_email or '(Default / Unspecified)'})...")
                try:
                    gmail_res = await create_draft(
                        subject="📊 Weekly App Review Pulse — Groww",
                        body_html=report_html,
                        recipient=to_email,
                        doc_url=doc_url,
                        session=mcp_session,
                    )
                    delivery_results["gmail"] = gmail_res
                    print("   ✅ Gmail draft created successfully.")
                except Exception as mail_err:
                    logger.warning("Failed to create Gmail draft: %s", mail_err)
                    delivery_results["gmail_error"] = str(mail_err)

        except MCPDeliveryError as mcp_err:
            logger.error("MCP delivery failed: %s", mcp_err)
            delivery_results["error"] = str(mcp_err)
        except Exception as exc:
            logger.error("Unexpected error during MCP delivery: %s", exc)
            delivery_results["error"] = str(exc)

    print("\n" + "=" * 75)
    print(" 🎉 PIPELINE EXECUTION COMPLETED")
    print("=" * 75)
    return {
        "reviews_count": len(reviews),
        "themes": themes,
        "quotes": quotes,
        "actions": actions,
        "markdown_file": str(md_file),
        "html_file": str(html_file),
        "delivery": delivery_results,
    }


def main():
    asyncio.run(run_pipeline())


if __name__ == "__main__":
    main()
