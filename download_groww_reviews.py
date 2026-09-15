#!/usr/bin/env python3
"""
Downloads real Google Play Store reviews for the Groww app (com.nextbillion.groww)
for the last 8 weeks, filters for >= 8 words and English language only, and saves to:
- data/reviews/latest.json
- data/exports/reviews.json
- data/exports/play_store.csv
"""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper import load_reviews, CACHE_FILE, EXPORTS_FILE, EXPORTS_CSV_FILE

GROWW_APP_ID = "com.nextbillion.groww"
WEEKS_LOOKBACK = 8
MIN_WORDS = 8


def main():
    print("=" * 65)
    print(f"Target App       : Groww ({GROWW_APP_ID})")
    print(f"Play Store URL   : https://play.google.com/store/apps/details?id={GROWW_APP_ID}&hl=en_IN")
    print(f"Time Window      : Last {WEEKS_LOOKBACK} weeks")
    print(f"Filters          : English language only & >= {MIN_WORDS} words")
    print("=" * 65)
    print("Connecting to Google Play Store and downloading reviews...")

    reviews = load_reviews(
        force_refresh=True,
        app_id=GROWW_APP_ID,
        weeks=WEEKS_LOOKBACK,
        min_words=MIN_WORDS,
    )

    print(f"\n✅ Successfully downloaded and filtered {len(reviews)} reviews for Groww!")
    print(f"📄 Saved primary cache : {CACHE_FILE}")
    print(f"📄 Saved export JSON   : {EXPORTS_FILE}")
    print(f"📄 Saved export CSV    : {EXPORTS_CSV_FILE}")

    if reviews:
        print("\n--- First 3 Filtered English Reviews ---")
        for i, rev in enumerate(reviews[:3], 1):
            words = len(rev.text.split())
            print(f"\n[{i}] Rating: ⭐ {rev.rating}/5 | Words: {words} | Date: {rev.date.strftime('%Y-%m-%d')}")
            print(f"    \"{rev.text[:140]}...\"")
    print("=" * 65)


if __name__ == "__main__":
    main()
