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
from src.agent.prompts import ACTION_GENERATOR_PROMPT

logger = logging.getLogger(__name__)


def _clean_json_str(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def _to_compact_context_text(raw_input: str) -> str:
    """Formats themes and quotes into concise text to minimize token consumption."""
    raw_input = raw_input.strip()
    try:
        data = json.loads(raw_input)
    except Exception:
        return raw_input

    lines = []
    if isinstance(data, dict):
        themes = data.get("themes", [])
        if themes:
            lines.append("Top Themes:")
            for i, t in enumerate(themes[:3]):
                name = t.get("name", "Feedback")
                desc = t.get("description", "")
                lines.append(f"{i+1}. {name}: {desc}")

        quotes = data.get("quotes", [])
        if quotes:
            lines.append("\nUser Quotes:")
            for q in quotes[:3]:
                theme = q.get("theme", "")
                text = q.get("text", "")
                rating = q.get("rating", 1)
                lines.append(f'- [{theme}] (★{rating}) "{text}"')

    if lines:
        return "\n".join(lines)
    return raw_input


class ActionGeneratorInput(BaseModel):
    themes_and_quotes_json: str = Field(description="JSON string or compact text of top themes and user quotes")


class ActionGeneratorTool(BaseTool):
    name: str = "ActionGeneratorTool"
    description: str = (
        "Given top themes and verbatim quotes, generates exactly 3 concrete, "
        "actionable product improvement ideas grounded in the review data. "
        "Returns JSON: {actions: [{title, description}]}"
    )
    args_schema: Type[BaseModel] = ActionGeneratorInput

    def _get_llm(self) -> BaseChatModel:
        return get_phase3_llm(temperature=0.3)

    def _run(self, themes_and_quotes_json: str) -> str:
        compact_context = _to_compact_context_text(themes_and_quotes_json)
        prompt_content = ACTION_GENERATOR_PROMPT.format(context_text=compact_context)
        llm = self._get_llm()

        for attempt in range(2):
            try:
                response = llm.invoke([HumanMessage(content=prompt_content)])
                raw_output = response.content if hasattr(response, "content") else str(response)
                cleaned = _clean_json_str(raw_output)
                data = json.loads(cleaned)

                if "actions" in data and isinstance(data["actions"], list):
                    actions = []
                    for a in data["actions"]:
                        title = str(a.get("title", "")).strip()
                        description = str(a.get("description", "")).strip()
                        if title and description:
                            actions.append({
                                "title": title,
                                "description": description,
                            })
                    if len(actions) >= 3:
                        return json.dumps({"actions": actions[:3]})
            except Exception as exc:
                logger.warning("ActionGeneratorTool attempt %d failed: %s", attempt + 1, exc)
                prompt_content += "\nCRITICAL: Return ONLY raw valid JSON with key 'actions' containing exactly 3 items."

        # Fallback default actions grounded in Groww domain
        fallback_actions = [
            {
                "title": "Automate KYC Verification & Status Tracking",
                "description": "Implement automated SLA breach notifications and real-time document validation checks to reduce verification delays.",
            },
            {
                "title": "Improve Payment & Auto-Refund Reconciliation",
                "description": "Deploy instantaneous webhook callbacks with payment gateways to auto-reconcile pending deposits and speed up refunds.",
            },
            {
                "title": "Optimize High-Frequency Chart Streaming",
                "description": "Upgrade candlestick chart websocket feeds to reduce rendering latency and eliminate freezes during market open hours.",
            },
        ]
        return json.dumps({"actions": fallback_actions})

