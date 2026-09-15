from datetime import date, datetime, timedelta
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class PulseGenerationError(ValueError):
    """Raised when pulse generation input is invalid or template rendering fails."""
    pass


def _validate_agent_output(agent_output: Any) -> None:
    """Validates the structure of agent_output before template rendering."""
    if not isinstance(agent_output, dict):
        raise PulseGenerationError("agent_output must be a dictionary.")

    required_keys = ["themes", "quotes", "actions"]
    for key in required_keys:
        if key not in agent_output:
            raise PulseGenerationError(f"agent_output is missing required key: '{key}'")
        if agent_output[key] is None:
            raise PulseGenerationError(f"agent_output key '{key}' cannot be None.")
        if not isinstance(agent_output[key], list):
            raise PulseGenerationError(f"agent_output['{key}'] must be a list.")

    for i, theme in enumerate(agent_output["themes"]):
        if not isinstance(theme, dict) or "name" not in theme or "description" not in theme:
            raise PulseGenerationError(f"Theme at index {i} must be a dict with 'name' and 'description'.")

    for i, quote in enumerate(agent_output["quotes"]):
        if not isinstance(quote, dict) or "text" not in quote:
            raise PulseGenerationError(f"Quote at index {i} must be a dict with 'text'.")

    for i, action in enumerate(agent_output["actions"]):
        if not isinstance(action, dict) or "title" not in action or "description" not in action:
            raise PulseGenerationError(f"Action at index {i} must be a dict with 'title' and 'description'.")


def _sanitize_markdown_text(text: str) -> str:
    """Escapes problematic Markdown control characters inside quotes if needed."""
    if not text:
        return ""
    # Strip unnecessary trailing/leading whitespace and newlines inside quote block
    cleaned = text.strip().replace("\n", " ")
    return cleaned


def generate_pulse(
    agent_output: dict,
    reviews: list,
    reference_date: date | datetime | None = None,
) -> dict[str, str]:
    """
    Transforms structured agent output into formatted Markdown and HTML weekly notes.

    Args:
        agent_output: Dictionary containing 'themes', 'quotes', and 'actions'.
        reviews: List of Review objects or dicts representing ingested reviews.
        reference_date: Optional date for deterministic testing. Defaults to today.

    Returns:
        Dictionary with keys 'markdown' and 'html'.

    Raises:
        PulseGenerationError: If agent_output is missing keys or template rendering fails.
    """
    _validate_agent_output(agent_output)

    if reference_date is None:
        ref_dt = date.today()
    elif isinstance(reference_date, datetime):
        ref_dt = reference_date.date()
    else:
        ref_dt = reference_date

    week_end = ref_dt.strftime("%b %d, %Y")
    week_start = (ref_dt - timedelta(days=7)).strftime("%b %d, %Y")

    # Sanitize quotes for safe markdown blockquote formatting
    sanitized_quotes = []
    for q in agent_output["quotes"][:3]:
        sanitized_quotes.append({
            "theme": q.get("theme", "General"),
            "text": _sanitize_markdown_text(q.get("text", "")),
            "rating": q.get("rating", 1),
        })

    context = {
        "week_start": week_start,
        "week_end": week_end,
        "review_count": len(reviews) if reviews is not None else 0,
        "top_themes": agent_output["themes"][:3],
        "quotes": sanitized_quotes,
        "actions": agent_output["actions"][:3],
    }

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    try:
        md_template = env.get_template("pulse.md.j2")
        markdown_content = md_template.render(**context)

        html_template = env.get_template("pulse.html.j2")
        html_content = html_template.render(**context)
    except Exception as exc:
        logger.error("Failed to render pulse templates: %s", exc)
        raise PulseGenerationError(f"Template rendering failed: {exc}") from exc

    return {
        "markdown": markdown_content,
        "html": html_content,
    }
