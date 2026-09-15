from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "scheduler_state.json"


@dataclass
class SchedulerState:
    last_run_timestamp: str | None = None
    last_run_iso_week: str | None = None
    processed_reviews_count: int = 0
    status: str = "idle"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchedulerState":
        return cls(
            last_run_timestamp=data.get("last_run_timestamp"),
            last_run_iso_week=data.get("last_run_iso_week"),
            processed_reviews_count=data.get("processed_reviews_count", 0),
            status=data.get("status", "idle"),
            details=data.get("details", {}),
        )


def get_current_iso_week(dt: datetime | None = None) -> str:
    """Returns the current ISO calendar week string, e.g. '2026-W38'."""
    target_dt = dt or datetime.now(timezone.utc)
    year, week, _ = target_dt.isocalendar()
    return f"{year}-W{week:02d}"


def load_state(state_file: Path | str | None = None) -> SchedulerState:
    """Loads the scheduler state from disk. Returns default state if file does not exist."""
    path = Path(state_file) if state_file else DEFAULT_STATE_FILE
    if not path.exists():
        return SchedulerState()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SchedulerState.from_dict(data)
    except Exception as exc:
        logger.warning("Could not read scheduler state from %s (%s). Starting fresh.", path, exc)
        return SchedulerState()


def save_state(state: SchedulerState, state_file: Path | str | None = None) -> None:
    """Persists the scheduler state to disk."""
    path = Path(state_file) if state_file else DEFAULT_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        logger.debug("Scheduler state successfully saved to %s", path)
    except Exception as exc:
        logger.error("Failed to save scheduler state to %s: %s", path, exc)


def is_already_run_this_week(
    state_file: Path | str | None = None,
    dt: datetime | None = None,
) -> bool:
    """
    Checks if a weekly pulse has already been completed for the current calendar week.
    Used to prevent accidental redundant duplicate runs.
    """
    state = load_state(state_file)
    current_week = get_current_iso_week(dt)
    return state.last_run_iso_week == current_week and state.status == "completed"
