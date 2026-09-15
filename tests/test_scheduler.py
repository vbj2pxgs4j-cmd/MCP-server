from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from src.scheduler import (
    SchedulerState,
    get_current_iso_week,
    is_already_run_this_week,
    load_state,
    run_scheduled_job,
    save_state,
)


@pytest.fixture
def temp_state_file(tmp_path):
    return tmp_path / "scheduler_state.json"


def test_state_load_save_roundtrip(temp_state_file):
    """Verify SchedulerState saves to and loads from JSON accurately."""
    state = SchedulerState(
        last_run_timestamp="2026-09-15T09:00:00Z",
        last_run_iso_week="2026-W38",
        processed_reviews_count=20,
        status="completed",
        details={"themes_count": 3},
    )
    save_state(state, temp_state_file)

    loaded = load_state(temp_state_file)
    assert loaded.last_run_iso_week == "2026-W38"
    assert loaded.processed_reviews_count == 20
    assert loaded.status == "completed"
    assert loaded.details["themes_count"] == 3


def test_load_state_non_existent_or_corrupt(temp_state_file):
    """Verify load_state returns fresh default state when file is missing or invalid."""
    missing = load_state(temp_state_file)
    assert missing.status == "idle"
    assert missing.last_run_iso_week is None

    # Corrupt file
    temp_state_file.write_text("invalid json content", encoding="utf-8")
    corrupt = load_state(temp_state_file)
    assert corrupt.status == "idle"


def test_deduplication_same_week(temp_state_file):
    """Verify is_already_run_this_week correctly detects completed runs in the same ISO week."""
    dt = datetime(2026, 9, 15, 9, 0, 0, tzinfo=timezone.utc)
    current_week = get_current_iso_week(dt)

    state = SchedulerState(
        last_run_iso_week=current_week,
        status="completed",
    )
    save_state(state, temp_state_file)

    assert is_already_run_this_week(temp_state_file, dt=dt) is True

    # Different week
    other_dt = datetime(2026, 9, 22, 9, 0, 0, tzinfo=timezone.utc)
    assert is_already_run_this_week(temp_state_file, dt=other_dt) is False


def test_run_scheduled_job_success_and_deduplication(temp_state_file):
    """Verify run_scheduled_job executes pipeline, updates state, and skips repeat execution."""
    mock_pipeline_res = {
        "reviews_count": 15,
        "themes": [{"name": "T1"}],
        "quotes": [{"text": "Q1"}],
        "actions": [{"title": "A1"}],
        "delivery": {"status": "ok"},
    }

    with patch("src.scheduler.runner.run_pipeline", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_pipeline_res

        # 1. First execution -> succeeds
        res1 = run_scheduled_job(force=False, deliver_mcp=False, state_file=temp_state_file)
        assert res1["status"] == "success"
        mock_run.assert_called_once()

        loaded_state = load_state(temp_state_file)
        assert loaded_state.status == "completed"
        assert loaded_state.processed_reviews_count == 15

        # 2. Immediate second execution without force -> skipped
        res2 = run_scheduled_job(force=False, deliver_mcp=False, state_file=temp_state_file)
        assert res2["status"] == "skipped"
        assert res2["reason"] == "already_run_this_week"

        # 3. Execution with force=True -> runs again
        res3 = run_scheduled_job(force=True, deliver_mcp=False, state_file=temp_state_file)
        assert res3["status"] == "success"
        assert mock_run.call_count == 2


def test_run_scheduled_job_failure_records_state(temp_state_file):
    """Verify run_scheduled_job records failed status on pipeline exception."""
    with patch("src.scheduler.runner.run_pipeline", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = RuntimeError("Scraper network timeout")

        res = run_scheduled_job(force=True, deliver_mcp=False, state_file=temp_state_file)
        assert res["status"] == "failed"
        assert "Scraper network timeout" in res["error"]

        state = load_state(temp_state_file)
        assert state.status == "failed"
        assert "Scraper network timeout" in state.details["error"]

