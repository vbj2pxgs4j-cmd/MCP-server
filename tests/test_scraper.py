import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.scraper import (
    Review,
    deduplicate,
    fetch_reviews,
    filter_reviews,
    is_valid_english_review,
    load_reviews,
    normalize,
)


def test_review_model_validates():
    """Verify that Review model instantiates and validates proper fields."""
    now = datetime.now(timezone.utc)
    rev = Review(
        id="rev-101",
        source="play_store",
        title="Great app",
        text="Smooth investment process and clean UI.",
        rating=5,
        date=now,
        language="en",
    )
    assert rev.id == "rev-101"
    assert rev.rating == 5
    assert rev.text == "Smooth investment process and clean UI."

    # Rating must be 1 to 5
    with pytest.raises(ValidationError):
        Review(
            id="rev-bad",
            text="Invalid rating",
            rating=6,
            date=now,
        )


def test_normalize_raw_review():
    """Verify normalization of raw Google Play Scraper dictionary."""
    now = datetime(2026, 9, 10, 14, 30, tzinfo=timezone.utc)
    raw = {
        "reviewId": "gp:AOqpTOE12345",
        "userName": "John Doe",
        "content": "KYC took a bit of time but resolved.",
        "score": 4,
        "replyContent": "Support Response",
        "at": now,
    }

    normalized = normalize(raw)
    assert normalized.id == "gp:AOqpTOE12345"
    assert normalized.text == "KYC took a bit of time but resolved."
    assert normalized.rating == 4
    assert normalized.title == "Support Response"
    assert normalized.date == now
    assert normalized.source == "play_store"


def test_deduplicate_reviews():
    """Verify deduplication preserves first occurrence and removes duplicates."""
    now = datetime.now(timezone.utc)
    rev1 = Review(id="1", text="Review 1", rating=5, date=now)
    rev2 = Review(id="2", text="Review 2", rating=4, date=now)
    rev3 = Review(id="1", text="Review 1 Duplicate", rating=3, date=now)

    deduped = deduplicate([rev1, rev2, rev3])
    assert len(deduped) == 2
    assert [r.id for r in deduped] == ["1", "2"]
    assert deduped[0].text == "Review 1"


def test_word_count_and_language_filtering():
    """Verify reviews with < 8 words or non-English content are filtered out."""
    now = datetime.now(timezone.utc)

    # 1. Short review (< 8 words)
    assert not is_valid_english_review("Good app works fine for me", min_words=8)

    # 2. Devanagari Hindi review
    assert not is_valid_english_review("बहुत ही अच्छा ऍप है मैंने बहुत पैसे कमाए और इन्वेस्ट किये", min_words=8)

    # 3. Hinglish review
    assert not is_valid_english_review("ye app bahut hi bekar hai koi download mat karna paise phas gaye", min_words=8)

    # 4. Valid English review (>= 8 words)
    valid_text = "The account opening process was very smooth and customer support was very helpful."
    assert is_valid_english_review(valid_text, min_words=8)

    reviews = [
        Review(id="1", text="Too short text", rating=5, date=now),
        Review(id="2", text="बहुत ही अच्छा ऍप है मैंने बहुत पैसे कमाए और इन्वेस्ट किये", rating=5, date=now),
        Review(id="3", text="ye app bahut hi bekar hai koi download mat karna paise phas gaye", rating=1, date=now),
        Review(id="4", text=valid_text, rating=5, date=now),
    ]

    filtered = filter_reviews(reviews, min_words=8)
    assert len(filtered) == 1
    assert filtered[0].id == "4"
    assert filtered[0].text == valid_text


def test_fetch_reviews_date_filtering():
    """Verify fetch_reviews filters reviews older than the cutoff weeks."""
    now = datetime.now(timezone.utc)
    recent_date = now - timedelta(days=10)
    old_date = now - timedelta(weeks=12)

    mock_raw_reviews = [
        {"reviewId": "recent-1", "content": "Recent review with enough words to satisfy filtering", "score": 5, "at": recent_date},
        {"reviewId": "old-1", "content": "Old review with enough words to satisfy filtering", "score": 2, "at": old_date},
    ]

    with patch("src.scraper.play_store.reviews", return_value=(mock_raw_reviews, None)):
        results = fetch_reviews(app_id="com.nextbillion.groww", weeks=8)

        assert len(results) == 1
        assert results[0]["reviewId"] == "recent-1"


def test_cache_save_and_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify saving to cache and loading without re-scraping."""
    test_cache_file = tmp_path / "latest.json"
    monkeypatch.setattr("src.scraper.CACHE_FILE", test_cache_file)
    monkeypatch.setattr("src.scraper.CACHE_DIR", tmp_path)
    monkeypatch.setattr("src.scraper.EXPORTS_DIR", tmp_path)
    monkeypatch.setattr("src.scraper.EXPORTS_FILE", tmp_path / "reviews.json")

    now = datetime.now(timezone.utc)
    mock_raw = [
        {"reviewId": "r-1", "content": "Excellent application for regular stock and mutual fund investments.", "score": 5, "at": now},
        {"reviewId": "r-2", "content": "KYC verification failed repeatedly even after uploading correct documents.", "score": 1, "at": now},
    ]

    with patch("src.scraper.fetch_reviews", return_value=mock_raw) as mock_fetch:
        # First call: cache does not exist, fetch must be called
        reviews = load_reviews(force_refresh=False)
        assert len(reviews) == 2
        assert mock_fetch.call_count == 1
        assert test_cache_file.exists()

        # Check cache structure
        with open(test_cache_file, "r", encoding="utf-8") as f:
            cache_json = json.load(f)
        assert "scraped_at" in cache_json
        assert len(cache_json["reviews"]) == 2

        # Second call: cache is fresh (< 7 days), fetch must NOT be called
        reviews_cached = load_reviews(force_refresh=False)
        assert len(reviews_cached) == 2
        assert mock_fetch.call_count == 1  # count didn't increase
        assert reviews_cached[0].id == "r-1"


def test_force_refresh_bypasses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify force_refresh=True re-fetches even if cache exists."""
    test_cache_file = tmp_path / "latest.json"
    monkeypatch.setattr("src.scraper.CACHE_FILE", test_cache_file)
    monkeypatch.setattr("src.scraper.CACHE_DIR", tmp_path)
    monkeypatch.setattr("src.scraper.EXPORTS_DIR", tmp_path)
    monkeypatch.setattr("src.scraper.EXPORTS_FILE", tmp_path / "reviews.json")

    now = datetime.now(timezone.utc)
    mock_raw = [{"reviewId": "r-1", "content": "Great experience with seamless transactions and fast deposits everyday.", "score": 5, "at": now}]

    with patch("src.scraper.fetch_reviews", return_value=mock_raw) as mock_fetch:
        load_reviews(force_refresh=False)
        assert mock_fetch.call_count == 1

        # Now force refresh
        load_reviews(force_refresh=True)
        assert mock_fetch.call_count == 2


def test_corrupt_cache_triggers_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify corrupt JSON cache file is discarded and fresh fetch triggered."""
    test_cache_file = tmp_path / "latest.json"
    monkeypatch.setattr("src.scraper.CACHE_FILE", test_cache_file)
    monkeypatch.setattr("src.scraper.CACHE_DIR", tmp_path)
    monkeypatch.setattr("src.scraper.EXPORTS_DIR", tmp_path)
    monkeypatch.setattr("src.scraper.EXPORTS_FILE", tmp_path / "reviews.json")

    # Write invalid JSON
    test_cache_file.write_text("{ corrupted invalid json ...")

    now = datetime.now(timezone.utc)
    mock_raw = [{"reviewId": "r-fresh", "content": "Fresh data with valid English text and more than eight words.", "score": 4, "at": now}]

    with patch("src.scraper.fetch_reviews", return_value=mock_raw) as mock_fetch:
        reviews = load_reviews(force_refresh=False)
        assert len(reviews) == 1
        assert reviews[0].id == "r-fresh"
        assert mock_fetch.call_count == 1
