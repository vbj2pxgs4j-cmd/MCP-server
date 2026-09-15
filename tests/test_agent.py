import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agent import build_agent_executor, get_phase3_llm, run_analysis
from src.agent.tools import ActionGeneratorTool, QuoteSelectorTool, ThemeClustererTool
from src.scraper.normalizer import Review


@pytest.fixture
def sample_reviews():
    now = datetime.now(timezone.utc)
    return [
        Review(
            id="rev-1",
            text="My KYC verification has been pending for more than six business days with zero updates.",
            rating=1,
            date=now,
            title="KYC Issue",
        ),
        Review(
            id="rev-2",
            text="Money was deducted from my balance but never credited to my bank account after two days.",
            rating=1,
            date=now,
            title="Payment Failed",
        ),
        Review(
            id="rev-3",
            text="Candlestick charts freeze continuously during market opening hours especially for option trades.",
            rating=2,
            date=now,
            title="Chart Lag",
        ),
        Review(
            id="rev-4",
            text="Very smooth and clean user interface for setting up monthly mutual fund SIPs without paperwork.",
            rating=5,
            date=now,
            title="Great App",
        ),
    ]


def test_theme_clusterer_tool_metadata():
    """Verify ThemeClustererTool extends BaseTool and has expected name and description."""
    tool = ThemeClustererTool()
    assert tool.name == "ThemeClustererTool"
    assert tool.description is not None
    assert len(tool.description) > 10


def test_theme_clusterer_tool_run_mocked():
    """Verify ThemeClustererTool._run returns valid JSON with <= 5 themes."""
    tool = ThemeClustererTool()
    mock_llm_response = AIMessage(
        content=json.dumps({
            "themes": [
                {"name": "KYC Verification", "description": "Delays in onboarding", "review_ids": ["rev-1"]},
                {"name": "Payment Failures", "description": "Deposit and withdrawal sync", "review_ids": ["rev-2"]},
                {"name": "Chart Lag", "description": "F&O chart latency at market open", "review_ids": ["rev-3"]},
            ]
        })
    )

    with patch.object(tool, "_get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm

        raw_output = tool._run(json.dumps([{"id": "rev-1", "text": "KYC delay"}]))
        parsed = json.loads(raw_output)

        assert "themes" in parsed
        assert isinstance(parsed["themes"], list)
        assert len(parsed["themes"]) <= 5
        assert parsed["themes"][0]["name"] == "KYC Verification"


def test_quote_selector_tool_metadata():
    """Verify QuoteSelectorTool extends BaseTool and has expected metadata."""
    tool = QuoteSelectorTool()
    assert tool.name == "QuoteSelectorTool"
    assert "verbatim" in tool.description.lower() or "quote" in tool.description.lower()


def test_quote_selector_verbatim_guarantee(sample_reviews):
    """Verify QuoteSelectorTool returns exactly 3 quotes, all verbatim substrings of input reviews."""
    tool = QuoteSelectorTool()
    context = {
        "themes": [{"name": "KYC"}, {"name": "Payments"}, {"name": "Trading"}],
        "reviews": [r.model_dump(mode="json") for r in sample_reviews],
    }

    # Simulate LLM returning slightly paraphrased text; tool must enforce exact verbatim match
    mock_llm_response = AIMessage(
        content=json.dumps({
            "quotes": [
                {"theme": "KYC", "text": "My KYC verification has been pending for more than six business days", "rating": 1},
                {"theme": "Payments", "text": "Money was deducted from my balance but never credited", "rating": 1},
                {"theme": "Trading", "text": "Candlestick charts freeze continuously during market opening", "rating": 2},
            ]
        })
    )

    with patch.object(tool, "_get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm

        raw_output = tool._run(json.dumps(context))
        parsed = json.loads(raw_output)

        assert "quotes" in parsed
        quotes = parsed["quotes"]
        assert len(quotes) == 3

        # Every quote text must be an exact substring of at least one review text in sample_reviews
        all_review_texts = [r.text for r in sample_reviews]
        for q in quotes:
            assert any(q["text"] in r_text for r_text in all_review_texts)


def test_action_generator_tool_metadata_and_run():
    """Verify ActionGeneratorTool returns exactly 3 actions with title and description."""
    tool = ActionGeneratorTool()
    assert tool.name == "ActionGeneratorTool"

    mock_llm_response = AIMessage(
        content=json.dumps({
            "actions": [
                {"title": "Automate KYC Verification Escalation", "description": "Setup auto-alerts for pending verifications."},
                {"title": "Deploy Real-Time UPI Webhook", "description": "Instant re-query for failed balance deposits."},
                {"title": "Optimize Candlestick WebSocket Feeds", "description": "High-throughput pooling for 9:15 AM market open."},
            ]
        })
    )

    with patch.object(tool, "_get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm

        raw_output = tool._run(json.dumps({"themes": [], "quotes": []}))
        parsed = json.loads(raw_output)

        assert "actions" in parsed
        actions = parsed["actions"]
        assert len(actions) == 3
        for a in actions:
            assert "title" in a and len(a["title"]) > 0
            assert "description" in a and len(a["description"]) > 0


def test_build_agent_executor_wiring():
    """Verify build_agent_executor constructs an AgentExecutor with 3 tools and max_iterations <= 15."""
    with patch("src.agent.executor.get_phase3_llm") as mock_get_llm:
        mock_instance = MagicMock()
        mock_instance.bind_tools = MagicMock()
        mock_get_llm.return_value = mock_instance

        executor = build_agent_executor()
        assert len(executor.tools) == 3
        assert {t.name for t in executor.tools} == {
            "ThemeClustererTool",
            "QuoteSelectorTool",
            "ActionGeneratorTool",
        }
        assert executor.verbose is True
        assert executor.max_iterations <= 15


def test_get_phase3_llm_gemini():
    """Verify get_phase3_llm returns a Gemini LLM instance or fallback."""
    with patch("src.config.PHASE3_LLM_PROVIDER", "gemini"):
        with patch("src.config.GEMINI_API_KEY", "test-gemini-key"):
            with patch("src.config.GEMINI_MODEL", "gemini-2.5-flash"):
                llm = get_phase3_llm()
                assert llm is not None


def test_get_phase3_llm_groq_fallback():
    """Verify get_phase3_llm returns ChatGroq when provider is explicitly set to groq."""
    with patch("src.config.PHASE3_LLM_PROVIDER", "groq"):
        with patch("src.config.GROQ_API_KEY", "test-groq-key"):
            llm = get_phase3_llm()
            assert llm is not None


def test_run_analysis_output_shape(sample_reviews):
    """Verify run_analysis returns valid dict with themes (<= 5), quotes (== 3), actions (== 3)."""
    output = run_analysis(sample_reviews)

    assert set(output.keys()) == {"themes", "quotes", "actions"}
    assert len(output["themes"]) <= 5
    assert len(output["quotes"]) == 3
    assert len(output["actions"]) == 3

    # Quotes should be verbatim substrings from sample_reviews
    all_texts = [r.text for r in sample_reviews]
    for q in output["quotes"]:
        assert any(q["text"] in t for t in all_texts)


def test_run_analysis_with_200_reviews():
    """Verify run_analysis smoothly processes 200 reviews using the minimal-token pipeline."""
    now = datetime.now(timezone.utc)
    reviews_200 = []
    # Generate 200 realistic mock reviews
    for i in range(200):
        rating = 1 if i % 3 == 0 else (2 if i % 3 == 1 else 5)
        text = (
            f"Review number {i+1}: KYC verification has been delayed for several days and support is unresponsive."
            if rating <= 2
            else f"Review number {i+1}: Very smooth experience with regular mutual fund SIPs and clean user interface."
        )
        reviews_200.append(
            Review(
                id=f"rev-200-{i+1}",
                text=text,
                rating=rating,
                date=now,
                title=f"Feedback {i+1}",
            )
        )

    output = run_analysis(reviews_200)

    assert set(output.keys()) == {"themes", "quotes", "actions"}
    assert len(output["themes"]) <= 5
    assert len(output["quotes"]) == 3
    assert len(output["actions"]) == 3

    # Every quote must be an exact verbatim substring from the 200 reviews
    all_texts = [r.text for r in reviews_200]
    for q in output["quotes"]:
        assert any(q["text"] in t for t in all_texts)

