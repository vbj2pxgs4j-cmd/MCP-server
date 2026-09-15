#!/usr/bin/env python3
"""
Weekly App Review Pulse — Automated Scheduler Runner.

Executes the recurring weekly cycle:
1. Ingests new Play Store reviews from the previous 7-day lookback window.
2. AI Agent clusters operational themes, selects verbatim quotes, and drafts action items.
3. Pulse Generator renders Markdown & HTML notes.
4. Delivers the note by updating Google Docs and creating a Gmail draft via MCP.
5. Updates execution state in `data/scheduler_state.json`.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import logging
import signal
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.orchestrator import run_pipeline
from src.scheduler.state import (
    SchedulerState,
    get_current_iso_week,
    is_already_run_this_week,
    load_state,
    save_state,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")


def run_scheduled_job(
    force: bool = False,
    deliver_mcp: bool = True,
    state_file: Path | str | None = None,
) -> dict:
    """
    Executes a single cycle of the weekly review pulse pipeline,
    recording execution state and respecting weekly deduplication unless forced.
    """
    now = datetime.now(timezone.utc)
    current_week = get_current_iso_week(now)

    if not force and is_already_run_this_week(state_file=state_file):
        logger.info(
            "⏭️ Weekly pulse has already been executed for ISO week %s. Skipping (use --force to override).",
            current_week,
        )
        return {"status": "skipped", "reason": "already_run_this_week", "week": current_week}

    logger.info("🚀 Triggering Weekly App Review Pulse job for week %s...", current_week)
    state = load_state(state_file=state_file)
    state.status = "running"
    state.last_run_timestamp = now.isoformat()
    save_state(state, state_file=state_file)

    try:
        pipeline_result = asyncio.run(
            run_pipeline(
                force_refresh_reviews=True,
                deliver_mcp=deliver_mcp,
            )
        )

        state.status = "completed"
        state.last_run_iso_week = current_week
        state.processed_reviews_count = pipeline_result.get("reviews_count", 0)
        state.details = {
            "themes_count": len(pipeline_result.get("themes", [])),
            "quotes_count": len(pipeline_result.get("quotes", [])),
            "actions_count": len(pipeline_result.get("actions", [])),
            "delivery": pipeline_result.get("delivery", {}),
        }
        save_state(state, state_file=state_file)
        logger.info("✅ Weekly pulse job completed successfully for week %s.", current_week)
        return {"status": "success", "result": pipeline_result}

    except Exception as exc:
        logger.error("❌ Scheduled pulse job failed: %s", exc)
        state.status = "failed"
        state.details = {"error": str(exc)}
        save_state(state, state_file=state_file)
        return {"status": "failed", "error": str(exc)}


def start_scheduler_daemon(
    check_interval_seconds: int = 60,
    target_weekday: int = 0,  # 0 = Monday
    target_hour: int = 9,      # 09:00 AM UTC
    target_minute: int = 0,
    deliver_mcp: bool = True,
) -> None:
    """
    Starts a persistent daemon checking every interval if the weekly pulse should run.
    Runs every Monday at 09:00 UTC (or user-configured schedule).
    """
    logger.info(
        "⏳ Weekly Pulse Daemon active. Target: Weekday %d at %02d:%02d UTC (Check interval: %ds).",
        target_weekday,
        target_hour,
        target_minute,
        check_interval_seconds,
    )

    running = True

    def _handle_exit(sig, frame):
        nonlocal running
        logger.info("Received termination signal %s. Shutting down scheduler gracefully...", sig)
        running = False

    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)

    while running:
        now = datetime.now(timezone.utc)
        is_target_time = (
            now.weekday() == target_weekday
            and now.hour == target_hour
            and now.minute == target_minute
        )

        if is_target_time and not is_already_run_this_week():
            logger.info("⏰ Scheduled trigger condition met! Running weekly pulse...")
            run_scheduled_job(force=False, deliver_mcp=deliver_mcp)

        time.sleep(check_interval_seconds)

    logger.info("Scheduler daemon stopped.")


def main():
    parser = argparse.ArgumentParser(description="Weekly App Review Pulse Scheduler")
    parser.add_argument("--now", action="store_true", help="Trigger pipeline execution immediately")
    parser.add_argument("--daemon", action="store_true", help="Run as persistent background scheduler daemon")
    parser.add_argument("--force", action="store_true", help="Force execution even if already run this week")
    parser.add_argument("--no-mcp", action="store_true", help="Skip MCP delivery during execution")
    parser.add_argument("--interval", type=int, default=60, help="Daemon check interval in seconds (default: 60)")

    args = parser.parse_args()

    deliver_mcp = not args.no_mcp

    if args.now:
        result = run_scheduled_job(force=args.force, deliver_mcp=deliver_mcp)
        if result["status"] == "failed":
            sys.exit(1)
    elif args.daemon:
        start_scheduler_daemon(
            check_interval_seconds=args.interval,
            deliver_mcp=deliver_mcp,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
