import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import config
from src.scraper.normalizer import (
    Review,
    deduplicate,
    export_reviews_to_csv,
    filter_reviews,
    is_valid_english_review,
    normalize,
)
from src.scraper.play_store import fetch_reviews

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = ROOT_DIR / "data" / "reviews"
CACHE_FILE = CACHE_DIR / "latest.json"
EXPORTS_DIR = ROOT_DIR / "data" / "exports"
EXPORTS_FILE = EXPORTS_DIR / "reviews.json"
EXPORTS_CSV_FILE = EXPORTS_DIR / "play_store.csv"
CACHE_MAX_AGE_DAYS = 7
MIN_REVIEW_WORDS = 8


def _is_cache_valid(cache_path: Path, max_age_days: int = CACHE_MAX_AGE_DAYS) -> tuple[bool, dict | None]:
    """
    Validates if cache file exists, is valid JSON, contains scraped_at, and is within max_age_days.
    Returns (is_valid, parsed_data_or_none).
    """
    if not cache_path.exists():
        return False, None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "scraped_at" not in data or "reviews" not in data:
            logger.warning("Cache file %s is missing required structure or scraped_at.", cache_path)
            return False, None

        scraped_at_raw = data["scraped_at"]
        if isinstance(scraped_at_raw, str):
            scraped_at = datetime.fromisoformat(scraped_at_raw.replace("Z", "+00:00"))
        else:
            return False, None

        now = datetime.now(timezone.utc)
        if scraped_at.tzinfo is None:
            scraped_at = scraped_at.replace(tzinfo=timezone.utc)

        if now - scraped_at < timedelta(days=max_age_days):
            return True, data
        else:
            logger.info("Cache in %s is older than %d days (%s). Expired.", cache_path, max_age_days, scraped_at)
            return False, None

    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("Failed to read cache %s: %s. Refreshing cache.", cache_path, exc)
        return False, None


def load_reviews(
    force_refresh: bool = False,
    app_id: str | None = None,
    weeks: int | None = None,
    min_words: int = MIN_REVIEW_WORDS,
) -> list[Review]:
    """
    Loads normalized Play Store reviews filtered to English-only and >= min_words words.
    Uses cached latest.json if < 7 days old, otherwise scrapes from Play Store,
    normalizes, filters, caches, and returns.
    Saves to data/reviews/latest.json, data/exports/reviews.json, and data/exports/play_store.csv.
    """
    target_app = app_id or config.TARGET_APP_ID
    target_weeks = weeks if weeks is not None else config.REVIEW_WINDOW_WEEKS

    if not force_refresh:
        valid, cached_data = _is_cache_valid(CACHE_FILE)
        if valid and cached_data:
            try:
                raw_cached = [Review.model_validate(item) for item in cached_data.get("reviews", [])]
                filtered_cached = filter_reviews(raw_cached, min_words=min_words)
                logger.info("Loaded %d filtered reviews from cache: %s", len(filtered_cached), CACHE_FILE)
                # Ensure CSV export exists even if loaded from cache
                if not EXPORTS_CSV_FILE.exists() or EXPORTS_CSV_FILE.stat().st_size == 0:
                    export_reviews_to_csv(filtered_cached, EXPORTS_CSV_FILE)
                return filtered_cached
            except Exception as e:
                logger.warning("Cache deserialization failed: %s. Re-scraping.", e)

    logger.info("Scraping fresh reviews for app=%s, weeks=%d", target_app, target_weeks)
    raw_reviews = fetch_reviews(app_id=target_app, weeks=target_weeks)

    normalized: list[Review] = []
    for raw in raw_reviews:
        try:
            normalized.append(normalize(raw))
        except Exception as err:
            logger.debug("Skipping unparseable review: %s", err)

    unique_reviews = deduplicate(normalized)

    # Filter: >= min_words and English language only
    filtered = filter_reviews(unique_reviews, min_words=min_words)
    logger.info(
        "Filtered reviews: %d passed (out of %d unique) for min_words=%d and English language",
        len(filtered),
        len(unique_reviews),
        min_words,
    )

    # 1. Save to primary cache (data/reviews/latest.json)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_payload = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "reviews": [r.model_dump(mode="json") for r in filtered],
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_payload, f, indent=2, default=str)
        logger.info("Persisted %d reviews to cache: %s", len(filtered), CACHE_FILE)
    except OSError as exc:
        logger.error("Failed to write cache to %s: %s", CACHE_FILE, exc)

    # 2. Save JSON export copy to data/exports/reviews.json
    try:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(EXPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_payload, f, indent=2, default=str)
        logger.info("Exported reviews JSON to: %s", EXPORTS_FILE)
    except OSError as exc:
        logger.warning("Failed to write export JSON to %s: %s", EXPORTS_FILE, exc)

    # 3. Save CSV export copy to data/exports/play_store.csv
    try:
        export_reviews_to_csv(filtered, EXPORTS_CSV_FILE)
        logger.info("Exported %d reviews to CSV: %s", len(filtered), EXPORTS_CSV_FILE)
    except Exception as exc:
        logger.error("Failed to write CSV export to %s: %s", EXPORTS_CSV_FILE, exc)

    return filtered


if __name__ == "__main__":
    print("🚀 Fetching real reviews for Groww (last 8 weeks)...")
    fetched = load_reviews(force_refresh=True, weeks=8, min_words=8)
    print(f"✅ Successfully fetched and filtered {len(fetched)} reviews!")
    print(f"📁 Primary cache : {CACHE_FILE}")
    print(f"📁 Export JSON   : {EXPORTS_FILE}")
    print(f"📁 Export CSV    : {EXPORTS_CSV_FILE}")
    if fetched:
        sample = fetched[0]
        word_count = len(sample.text.split())
        print(f"\n🔍 Sample Review ({word_count} words):")
        print(f"   ID     : {sample.id}")
        print(f"   Rating : ⭐ {sample.rating}/5")
        print(f"   Date   : {sample.date}")
        print(f"   Text   : {sample.text[:120]}...")
