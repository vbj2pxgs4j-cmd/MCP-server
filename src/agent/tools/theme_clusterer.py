import json
import logging
import re
from typing import Any, Type

from langchain.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src import config
from src.agent.llm import get_phase3_llm
from src.agent.prompts import THEME_CLUSTERER_PROMPT

logger = logging.getLogger(__name__)


def _clean_json_str(text: str) -> str:
    """Strips markdown code fences and extraneous text from an LLM response."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _to_compact_reviews_text(raw_input: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Parses input reviews (either JSON string or compact text) and formats into
    ultra-dense single lines: '[id] (★rating) text' to minimize Groq token usage.
    Returns (compact_text, parsed_reviews_list).
    """
    raw_input = raw_input.strip()
    parsed_reviews: list[dict[str, Any]] = []

    # Check if input is a JSON string
    if raw_input.startswith("[") or raw_input.startswith("{"):
        try:
            data = json.loads(raw_input)
            if isinstance(data, list):
                parsed_reviews = [r for r in data if isinstance(r, dict)]
            elif isinstance(data, dict) and "reviews" in data and isinstance(data["reviews"], list):
                parsed_reviews = [r for r in data["reviews"] if isinstance(r, dict)]
        except Exception:
            pass

    if parsed_reviews:
        lines = []
        for i, r in enumerate(parsed_reviews):
            rid = str(r.get("id", f"r{i+1}"))
            rating = r.get("rating", 3)
            text = str(r.get("text", "")).strip()
            lines.append(f"[{rid}] (★{rating}) {text}")
        return "\n".join(lines), parsed_reviews

    # Already formatted text
    return raw_input, []


class ThemeClustererInput(BaseModel):
    reviews_json: str = Field(description="Reviews data as compact text or JSON array with id, rating, text")


class ThemeClustererTool(BaseTool):
    name: str = "ThemeClustererTool"
    description: str = (
        "Given app reviews (compact text or JSON), clusters them into at most 5 "
        "named operational themes with mapped review_ids. Returns JSON: {themes: [{name, description, review_ids[]}]}"
    )
    args_schema: Type[BaseModel] = ThemeClustererInput

    def _get_llm(self) -> BaseChatModel:
        return get_phase3_llm(temperature=0.3)

    def _run(self, reviews_json: str) -> str:
        compact_text, parsed_reviews = _to_compact_reviews_text(reviews_json)
        prompt_content = THEME_CLUSTERER_PROMPT.format(reviews_text=compact_text)
        llm = self._get_llm()

        for attempt in range(2):
            try:
                response = llm.invoke([HumanMessage(content=prompt_content)])
                raw_output = response.content if hasattr(response, "content") else str(response)
                cleaned = _clean_json_str(raw_output)
                data = json.loads(cleaned)

                if "themes" in data and isinstance(data["themes"], list):
                    themes = data["themes"][:5]
                    normalized_themes = []
                    for t in themes:
                        normalized_themes.append({
                            "name": str(t.get("name", "General Feedback")),
                            "description": str(t.get("description", "")),
                            "review_ids": list(t.get("review_ids", [])),
                        })
                    return json.dumps({"themes": normalized_themes})

            except Exception as exc:
                logger.warning("ThemeClustererTool attempt %d error: %s", attempt + 1, exc)
                prompt_content += "\nCRITICAL: Return ONLY valid JSON with key 'themes'. No markdown fences."

        # Fallback heuristic if LLM unavailable
        fallback_ids = [r.get("id", str(i)) for i, r in enumerate(parsed_reviews[:10])] if parsed_reviews else ["rev-1"]
        fallback_themes = [
            {
                "name": "General App Feedback",
                "description": "User feedback regarding app functionality, onboarding, and service reliability.",
                "review_ids": fallback_ids,
            }
        ]
        return json.dumps({"themes": fallback_themes})

