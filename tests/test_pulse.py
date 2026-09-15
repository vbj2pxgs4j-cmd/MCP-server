from datetime import date, datetime, timezone
import pytest

from src.pulse import PulseGenerationError, generate_pulse
from src.scraper.normalizer import Review


@pytest.fixture
def sample_agent_output():
    return {
        "themes": [
            {
                "name": "KYC & Account Onboarding",
                "description": "Users report lengthy delays in KYC verification and document mismatch errors.",
            },
            {
                "name": "Payments & Withdrawal Sync",
                "description": "UPI payment debited from bank but wallet balance update delayed by hours.",
            },
            {
                "name": "Trading Execution & Chart Lag",
                "description": "Candlestick charts freeze during 9:15 AM market opening spikes.",
            },
        ],
        "quotes": [
            {
                "theme": "KYC & Account Onboarding",
                "text": "My KYC verification has been pending for more than six business days with zero updates.",
                "rating": 1,
            },
            {
                "theme": "Payments & Withdrawal Sync",
                "text": "Money was deducted from my balance but never credited to my bank account after two days.",
                "rating": 1,
            },
            {
                "theme": "Trading Execution & Chart Lag",
                "text": "Candlestick charts freeze continuously during market opening hours especially for option trades.",
                "rating": 2,
            },
        ],
        "actions": [
            {
                "title": "Automate KYC Status Tracker",
                "description": "Introduce real-time stage-by-stage document verification progress tracker in app.",
            },
            {
                "title": "Instant UPI Webhook Reconciliation",
                "description": "Implement fallback polling webhook reconciliation with payment gateways within 3 minutes.",
            },
            {
                "title": "Optimize WebSocket Chart Rendering",
                "description": "Throttling chart UI updates during high volatility market open to prevent main thread blocking.",
            },
        ],
    }


@pytest.fixture
def sample_reviews():
    now = datetime.now(timezone.utc)
    return [
        Review(
            id=f"rev-{i}",
            text=f"Review text number {i} with sufficient words to pass filter test.",
            rating=(i % 5) + 1,
            date=now,
        )
        for i in range(25)
    ]


def test_pulse_generation_success(sample_agent_output, sample_reviews):
    """Verify generate_pulse returns both markdown and html with expected structure."""
    result = generate_pulse(sample_agent_output, sample_reviews)

    assert "markdown" in result
    assert "html" in result
    assert isinstance(result["markdown"], str)
    assert isinstance(result["html"], str)


def test_markdown_required_sections_and_content(sample_agent_output, sample_reviews):
    """Criterion 4.3: Rendered Markdown includes all 3 required sections and all 3 items."""
    result = generate_pulse(sample_agent_output, sample_reviews)
    md = result["markdown"]

    # Check required section headers
    assert "Top Themes" in md
    assert "What Users Are Saying" in md
    assert "Action Ideas" in md

    # Check themes
    assert "KYC & Account Onboarding" in md
    assert "Payments & Withdrawal Sync" in md
    assert "Trading Execution & Chart Lag" in md

    # Check quotes
    assert "My KYC verification has been pending" in md
    assert "Money was deducted from my balance" in md
    assert "Candlestick charts freeze continuously" in md

    # Check actions
    assert "Automate KYC Status Tracker" in md
    assert "Instant UPI Webhook Reconciliation" in md
    assert "Optimize WebSocket Chart Rendering" in md


def test_date_range_calculation(sample_agent_output, sample_reviews):
    """Criterion 4.4 & EC-P03: Date range is today - 7 days to today across year boundaries."""
    ref_date = date(2026, 1, 3)
    result = generate_pulse(sample_agent_output, sample_reviews, reference_date=ref_date)
    md = result["markdown"]
    html = result["html"]

    # Week of Dec 27, 2025 – Jan 03, 2026 (or Jan 3, 2026)
    assert "2025" in md and "2026" in md
    assert "Dec 27, 2025" in md
    assert "Jan 03, 2026" in md or "Jan 3, 2026" in md
    assert "Dec 27, 2025" in html


def test_review_count_accuracy(sample_agent_output, sample_reviews):
    """Criterion 4.5: review_count in pulse matches number of reviews passed."""
    result = generate_pulse(sample_agent_output, sample_reviews)
    expected_count_str = str(len(sample_reviews))

    assert f"Reviews analysed: {expected_count_str}" in result["markdown"]
    assert expected_count_str in result["html"]


def test_html_template_inline_styles_and_sections(sample_agent_output, sample_reviews):
    """Criterion 4.2 & 4.6: HTML has inline styles, is > 500 chars, and contains all sections."""
    result = generate_pulse(sample_agent_output, sample_reviews)
    html = result["html"]

    assert len(html) > 500
    assert "style=" in html
    assert "Top Themes" in html
    assert "What Users Are Saying" in html
    assert "Action Ideas" in html
    assert "http://" not in html.split("<body")[0] or "<link rel=\"stylesheet\"" not in html


def test_missing_agent_output_keys_raises_error(sample_reviews):
    """EC-P01: Missing or None keys in agent_output raise PulseGenerationError."""
    with pytest.raises(PulseGenerationError):
        generate_pulse({}, sample_reviews)

    with pytest.raises(PulseGenerationError):
        generate_pulse({"themes": [], "quotes": None, "actions": []}, sample_reviews)

    with pytest.raises(PulseGenerationError):
        generate_pulse("invalid", sample_reviews)


def test_quote_sanitization_and_special_chars(sample_agent_output, sample_reviews):
    """EC-P02: Quotes with newlines and markdown symbols are formatted safely."""
    sample_agent_output["quotes"][0]["text"] = "Line 1\nLine 2 **bold** and #hash"
    result = generate_pulse(sample_agent_output, sample_reviews)
    assert "Line 1 Line 2 **bold** and #hash" in result["markdown"]


def test_large_input_payload_bounds(sample_agent_output, sample_reviews):
    """EC-P04: Extra long descriptions are safely bounded in HTML output."""
    sample_agent_output["themes"][0]["description"] = "A" * 3000
    result = generate_pulse(sample_agent_output, sample_reviews)
    # Ensure HTML is bounded and doesn't explode in size
    assert len(result["html"]) < 50_000
