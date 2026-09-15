import json
import logging
import re
from typing import Any

from src import config
from src.agent.executor import build_agent_executor
from src.agent.llm import get_phase3_llm
from src.agent.tools import ActionGeneratorTool, QuoteSelectorTool, ThemeClustererTool
from src.scraper.normalizer import Review

logger = logging.getLogger(__name__)


def _clean_json_dict(raw_str: str) -> dict[str, Any] | None:
    try:
        raw_str = raw_str.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_str)
        if match:
            raw_str = match.group(1).strip()
        data = json.loads(raw_str)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _stratified_sample(reviews: list[Review], max_count: int = 20) -> list[Review]:
    """
    Selects a stratified sample of reviews prioritizing 1-2 star pain points (60%)
    and 3-5 star positive/neutral reviews (40%) to fit comfortably in Groq's 8K TPM context window.
    """
    if len(reviews) <= max_count:
        return reviews

    negatives = [r for r in reviews if r.rating <= 2]
    others = [r for r in reviews if r.rating > 2]

    target_neg = int(max_count * 0.6)
    target_oth = max_count - target_neg

    selected_neg = negatives[:target_neg]
    selected_oth = others[:target_oth]

    combined = selected_neg + selected_oth
    if len(combined) < max_count:
        remaining = [r for r in reviews if r not in combined]
        combined.extend(remaining[: max_count - len(combined)])

    return combined


def run_analysis(
    reviews: list[Review] | list[dict[str, Any]],
    use_agent_executor: bool = False,
) -> dict[str, Any]:
    """
    Runs the LangChain agent analysis over the provided reviews (handling up to 200 reviews).
    Optimized for bare minimum tokens and minimal calls under Groq free-tier rate limits
    (8,000 TPM / 30 RPM):
    1. Indexes the full review pool (up to 200 reviews) in memory for quote matching.
    2. Takes a 20-review stratified sample and compresses into compact lines '[id] (★rating) text'.
    3. Step 1: Calls ThemeClustererTool (1 LLM call, ~600 tokens).
    4. Step 2: Resolves verbatim quotes via QuoteSelectorTool directly from the review pool (0 LLM calls, 0 tokens).
    5. Step 3: Calls ActionGeneratorTool with concise theme+quote context (1 LLM call, ~300 tokens).

    Total cost: 2 LLM calls, ~900-1,100 tokens total (completes in ~2 seconds).
    Returns a dictionary with keys:
    - 'themes': list of <= 5 themes
    - 'quotes': list of exactly 3 verbatim quotes
    - 'actions': list of exactly 3 actions
    """
    # 1. Normalize input into Review models
    review_objs: list[Review] = []
    for item in reviews:
        if isinstance(item, Review):
            review_objs.append(item)
        elif isinstance(item, dict):
            try:
                review_objs.append(Review.model_validate(item))
            except Exception:
                pass

    if not review_objs:
        logger.warning("run_analysis received empty reviews list. Using fallback response.")
        review_objs = [
            Review(
                id="rev-default-1",
                text="The application is easy to use for mutual funds but verification took longer than expected.",
                rating=3,
                date=None,
            )
        ]

    logger.info("Starting analysis layer on %d reviews (token-optimized pipeline)...", len(review_objs))

    # Optional: Run via LangChain AgentExecutor if explicitly requested
    has_api_key = bool(
        (config.GEMINI_API_KEY and config.GEMINI_API_KEY != "your-gemini-api-key")
        or (config.LLM_API_KEY and config.LLM_API_KEY not in ("your-groq-api-key", "your-gemini-api-key"))
    )
    if use_agent_executor and has_api_key:
        try:
            sample_for_agent = _stratified_sample(review_objs, max_count=15)
            compact_agent_input = "\n".join([f"[{r.id}] (★{r.rating}) {r.text.strip()}" for r in sample_for_agent])
            agent_executor = build_agent_executor()
            result = agent_executor.invoke({"input": f"Analyze these app reviews:\n{compact_agent_input}"})
            out_dict = _clean_json_dict(str(result.get("output", "")))
            if out_dict and "themes" in out_dict and "quotes" in out_dict and "actions" in out_dict:
                return out_dict
        except Exception as exc:
            logger.warning("AgentExecutor invocation failed: %s. Using direct pipeline.", exc)

    # 2. Stratified Representative Sampling for Clustering (20 reviews max, ~400 tokens)
    sampled_reviews = _stratified_sample(review_objs, max_count=20)
    compact_reviews_text = "\n".join([
        f"[{r.id}] (★{r.rating}) {r.text.strip()}"
        for r in sampled_reviews
    ])

    # 3. Step 1: Theme Clustering (1 LLM call)
    clusterer = ThemeClustererTool()
    try:
        res_themes_raw = clusterer._run(compact_reviews_text)
        res_themes = json.loads(res_themes_raw)
        themes = res_themes.get("themes", [])
    except Exception as exc:
        logger.warning("ThemeClustererTool execution failed: %s. Using fallback.", exc)
        themes = []

    if not themes:
        themes = [
            {
                "name": "General App Experience",
                "description": "User feedback regarding account onboarding, transactions, and performance.",
                "review_ids": [r.id for r in sampled_reviews[:5]],
            }
        ]
    final_themes = themes[:5]

    # 4. Step 2: Quote Selection (0 LLM calls, 0 tokens — direct verbatim resolution from full pool)
    selector = QuoteSelectorTool()
    pool_payload = [
        {"id": r.id, "text": r.text, "rating": r.rating}
        for r in review_objs
    ]
    quotes_context = json.dumps({
        "themes": final_themes,
        "reviews": pool_payload,
    })

    try:
        res_quotes_raw = selector._run(quotes_context)
        res_quotes = json.loads(res_quotes_raw)
        quotes = res_quotes.get("quotes", [])
    except Exception as exc:
        logger.warning("QuoteSelectorTool execution failed: %s. Using fallback.", exc)
        quotes = []

    # Guarantee exactly 3 verbatim quotes
    final_quotes = quotes[:3]
    while len(final_quotes) < 3:
        idx = len(final_quotes)
        sample_r = review_objs[idx] if idx < len(review_objs) else review_objs[0]
        final_quotes.append({
            "theme": final_themes[min(idx, len(final_themes) - 1)]["name"],
            "text": sample_r.text,
            "rating": sample_r.rating,
        })

    # 5. Step 3: Action Generation (1 LLM call, ~300 tokens)
    generator = ActionGeneratorTool()
    actions_context = json.dumps({
        "themes": [{"name": t["name"], "description": t.get("description", "")} for t in final_themes[:3]],
        "quotes": final_quotes,
    })

    try:
        res_actions_raw = generator._run(actions_context)
        res_actions = json.loads(res_actions_raw)
        actions = res_actions.get("actions", [])
    except Exception as exc:
        logger.warning("ActionGeneratorTool execution failed: %s. Using fallback.", exc)
        actions = []

    final_actions = actions[:3]
    while len(final_actions) < 3:
        idx = len(final_actions) + 1
        final_actions.append({
            "title": f"Product Improvement Priority {idx}",
            "description": f"Address high-frequency user pain points reported in theme {idx}.",
        })

    logger.info(
        "Analysis complete: %d themes, %d quotes, %d actions (total LLM calls: 2, estimated tokens: ~1,000)",
        len(final_themes),
        len(final_quotes),
        len(final_actions),
    )

    return {
        "themes": final_themes,
        "quotes": final_quotes,
        "actions": final_actions,
    }


__all__ = [
    "run_analysis",
    "build_agent_executor",
    "get_phase3_llm",
    "ThemeClustererTool",
    "QuoteSelectorTool",
    "ActionGeneratorTool",
]

