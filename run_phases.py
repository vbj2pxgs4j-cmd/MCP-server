#!/usr/bin/env python3
"""
Executes Phase 2 (Review Ingestion) and Phase 3 (LangChain AI Agent Analysis),
and displays and saves the generated Weekly Review Pulse Report.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from src import config
from src.agent import run_analysis
from src.scraper import load_reviews


def run_pipeline() -> dict:
    print("=" * 70)
    print(" 🚀 WEEKLY APP REVIEW PULSE — PHASES 2 & 3 PIPELINE")
    print("=" * 70)

    # -------------------------------------------------------------
    # 1. PHASE 2: INGESTION & DATA PREPARATION
    # -------------------------------------------------------------
    print("\n📦 [PHASE 2] Loading & Ingesting App Reviews...")
    print(f"   Target App ID   : {config.TARGET_APP_ID}")
    print(f"   Lookback Window : {config.REVIEW_WINDOW_WEEKS} weeks")

    # Load reviews from scraper (uses latest.json cache or fetches from Play Store)
    reviews = load_reviews(force_refresh=False)
    print(f"   ✅ Ingested {len(reviews)} reviews successfully.")

    if not reviews:
        print("   ⚠️ No reviews found. Please run download_groww_reviews.py first.")
        return {}

    # Calculate review metrics
    ratings_count = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews:
        ratings_count[r.rating] = ratings_count.get(r.rating, 0) + 1

    print(f"   Rating breakdown: 1★: {ratings_count[1]} | 2★: {ratings_count[2]} | "
          f"3★: {ratings_count[3]} | 4★: {ratings_count[4]} | 5★: {ratings_count[5]}")

    # -------------------------------------------------------------
    # 2. PHASE 3: AI AGENT ANALYSIS
    # -------------------------------------------------------------
    print("\n🤖 [PHASE 3] Running AI Agent Analysis...")
    has_gemini = bool(config.GEMINI_API_KEY and config.GEMINI_API_KEY != "your-gemini-api-key")
    has_groq = bool(config.GROQ_API_KEY and config.GROQ_API_KEY != "your-groq-api-key")

    if has_gemini:
        print(f"   Provider : Gemini ({config.GEMINI_MODEL})")
    elif has_groq:
        print(f"   Provider : Groq ({config.GROQ_MODEL}) [Fallback / Phase 2 key]")
    else:
        print("   Provider : Heuristic Mode (No active LLM API key detected)")

    print(f"   Analyzing {min(len(reviews), 200)} reviews through clustering and synthesis...")
    analysis_output = run_analysis(reviews)

    themes = analysis_output.get("themes", [])
    quotes = analysis_output.get("quotes", [])
    actions = analysis_output.get("actions", [])

    print(f"   ✅ Analysis complete: {len(themes)} themes, {len(quotes)} quotes, {len(actions)} actions.")

    # -------------------------------------------------------------
    # 3. PHASE 4: PULSE GENERATION (MARKDOWN & HTML)
    # -------------------------------------------------------------
    print("\n📝 [PHASE 4] Generating Weekly Pulse Notes (Markdown + HTML)...")
    from src.pulse import generate_pulse

    pulse_output = generate_pulse(analysis_output, reviews)
    report_md = pulse_output["markdown"]
    report_html = pulse_output["html"]

    # Print Report to console
    print("\n" + "=" * 70)
    print(" 📊 GENERATED WEEKLY APP REVIEW PULSE REPORT (MARKDOWN)")
    print("=" * 70 + "\n")
    print(report_md)
    print("=" * 70)

    # Save Markdown to file
    md_file = ROOT_DIR / "data" / "weekly_pulse.md"
    md_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.write_text(report_md, encoding="utf-8")
    print(f"\n💾 Markdown saved to: {md_file}")

    # Also keep legacy filename weekly_pulse_report.md for compatibility
    (ROOT_DIR / "data" / "weekly_pulse_report.md").write_text(report_md, encoding="utf-8")

    # Save HTML to file
    html_file = ROOT_DIR / "data" / "weekly_pulse.html"
    html_file.write_text(report_html, encoding="utf-8")
    print(f"💾 HTML email body saved to: {html_file}")

    # -------------------------------------------------------------
    # 4. PHASE 5: MCP DELIVERY (GOOGLE DOCS & GMAIL)
    # -------------------------------------------------------------
    delivery_info = {}
    print("\n📤 [PHASE 5] MCP Delivery Status:")
    print(f"   MCP Server Endpoint : {config.MCP_SERVER_URL}")
    if config.GOOGLE_DOC_ID:
        print(f"   Target Google Doc   : https://docs.google.com/document/d/{config.GOOGLE_DOC_ID}/edit")
    else:
        print("   Target Google Doc   : (Not set - configure GOOGLE_DOC_ID in .env to append)")
    if config.PULSE_RECIPIENT_EMAIL:
        print(f"   Pulse Email Recipient: {config.PULSE_RECIPIENT_EMAIL}")
    else:
        print("   Pulse Email Recipient: (Not set - configure PULSE_RECIPIENT_EMAIL in .env)")

    # If --deliver flag is provided, run async delivery
    if "--deliver" in sys.argv or "-d" in sys.argv:
        import asyncio
        from src.orchestrator import run_pipeline as run_orchestrator
        print("\n🚀 Executing live MCP delivery via orchestrator...")
        delivery_info = asyncio.run(run_orchestrator(deliver_mcp=True))

    return {
        "reviews_count": len(reviews),
        "themes": themes,
        "quotes": quotes,
        "actions": actions,
        "markdown": report_md,
        "html": report_html,
        "markdown_file": str(md_file),
        "html_file": str(html_file),
        "delivery": delivery_info,
    }


def _build_markdown_report(
    reviews: list,
    ratings: dict,
    themes: list[dict],
    quotes: list[dict],
    actions: list[dict],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    total_reviews = len(reviews)
    avg_rating = sum(r.rating for r in reviews) / total_reviews if total_reviews else 0.0

    lines = []
    lines.append(f"# 📊 Weekly Review Pulse — Groww App")
    lines.append(f"**Generated:** {now_str} | **Lookback Window:** Last {config.REVIEW_WINDOW_WEEKS} weeks")
    lines.append(f"**Analyzed:** {total_reviews} reviews | **Avg Rating:** ★ {avg_rating:.2f}/5.0\n")

    lines.append("## 📈 Rating Distribution")
    lines.append(f"- ⭐ 5 Stars: {ratings.get(5, 0)} ({ratings.get(5, 0)*100//max(total_reviews, 1)}%)")
    lines.append(f"- ⭐ 4 Stars: {ratings.get(4, 0)} ({ratings.get(4, 0)*100//max(total_reviews, 1)}%)")
    lines.append(f"- ⭐ 3 Stars: {ratings.get(3, 0)} ({ratings.get(3, 0)*100//max(total_reviews, 1)}%)")
    lines.append(f"- ⭐ 2 Stars: {ratings.get(2, 0)} ({ratings.get(2, 0)*100//max(total_reviews, 1)}%)")
    lines.append(f"- ⭐ 1 Star : {ratings.get(1, 0)} ({ratings.get(1, 0)*100//max(total_reviews, 1)}%)\n")

    lines.append("## 🔥 Top Operational Themes")
    for i, t in enumerate(themes[:5], 1):
        name = t.get("name", f"Theme {i}")
        desc = t.get("description", "")
        count = len(t.get("review_ids", []))
        lines.append(f"### {i}. {name}")
        lines.append(f"{desc}")
        if count > 0:
            lines.append(f"*Associated sample reviews: {count}*")
        lines.append("")

    lines.append("## 💬 Verbatim User Quotes")
    for i, q in enumerate(quotes[:3], 1):
        theme = q.get("theme", "General")
        text = q.get("text", "")
        rating = q.get("rating", 1)
        lines.append(f"> \"{text}\"")
        lines.append(f"— **★{rating}/5** | Theme: *{theme}*\n")

    lines.append("## 💡 Engineering & Product Action Ideas")
    for i, a in enumerate(actions[:3], 1):
        title = a.get("title", f"Action Item {i}")
        desc = a.get("description", "")
        lines.append(f"### {i}. {title}")
        lines.append(f"{desc}\n")

    return "\n".join(lines)


if __name__ == "__main__":
    run_pipeline()
