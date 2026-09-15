import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

# Pattern detecting non-Latin alphabets commonly present in app reviews (Indic, Cyrillic, CJK, Arabic, etc.)
NON_LATIN_SCRIPT_PATTERN = re.compile(
    r"[\u0900-\u097F"  # Devanagari (Hindi, Marathi, etc.)
    r"\u0980-\u09FF"  # Bengali
    r"\u0A00-\u0A7F"  # Gurmukhi
    r"\u0A80-\u0AFF"  # Gujarati
    r"\u0B00-\u0B7F"  # Oriya
    r"\u0B80-\u0BFF"  # Tamil
    r"\u0C00-\u0C7F"  # Telugu
    r"\u0C80-\u0CFF"  # Kannada
    r"\u0D00-\u0D7F"  # Malayalam
    r"\u0600-\u06FF"  # Arabic/Urdu
    r"\u0400-\u04FF"  # Cyrillic
    r"\u4E00-\u9FFF"  # CJK
    r"]"
)

# Common Romanized Hindi/Hinglish marker words
HINGLISH_WORDS = {
    "hai", "hain", "yeh", "ye", "aur", "nahi", "nhi", "nahin", "raha", "rha", "rahi", "rahe",
    "tha", "thi", "the", "bhi", "bohot", "bahut", "acha", "achha", "achhi", "bekar", "bakwas",
    "mat", "karna", "karo", "kare", "koi", "kuch", "kuchh", "mera", "meri", "mere", "mujhe",
    "hum", "hume", "aap", "aapko", "bhai", "paise", "paisa", "khata", "kyu", "kyun", "kya",
    "kaise", "diya", "de", "do", "lo", "lia", "liya", "chal", "chalta", "hua", "hui", "hue",
    "hota", "hoti", "hote", "gaya", "gayi", "gaye", "sabse", "sirf", "lekin", "par", "pe",
    "wala", "wali", "wale", "kariye", "dost", "yaha", "yahan", "waha", "wahan", "fraud", "chor"
}

# Core English vocabulary used for basic language verification
COMMON_ENGLISH_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not", "on",
    "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from", "they", "we",
    "say", "her", "she", "or", "an", "will", "my", "one", "all", "would", "there", "their",
    "what", "so", "up", "out", "if", "about", "who", "get", "which", "go", "me", "when",
    "make", "can", "like", "time", "no", "just", "him", "know", "take", "people", "into",
    "year", "your", "good", "some", "could", "them", "see", "other", "than", "then", "now",
    "look", "only", "come", "its", "over", "think", "also", "back", "after", "use", "two",
    "how", "our", "work", "first", "well", "way", "even", "new", "want", "because", "any",
    "these", "give", "day", "most", "us", "very", "app", "application", "groww", "stock",
    "stocks", "mutual", "fund", "funds", "money", "bank", "account", "payment", "charges",
    "charge", "fee", "fees", "kyc", "verification", "support", "customer", "worst", "bad",
    "great", "excellent", "nice", "slow", "fast", "easy", "update", "issue", "problem",
    "bug", "crashes", "crash", "interface", "experience", "investment", "investing", "invest",
    "trade", "trading", "transaction", "deposit", "withdrawal", "withdraw", "option", "options",
    "service", "help", "otp", "login", "please", "fix", "don't", "cant", "can't", "wont",
    "won't", "doesn't", "didn't", "haven't", "hasn't", "isnt", "isn't", "arent", "aren't",
    "smooth", "simple", "helpful", "better", "best", "super", "fine", "reliable", "trust",
    "platform", "wallet", "amount", "deducted", "refund", "time", "hours", "days", "still"
}


class Review(BaseModel):
    id: str
    source: str = "play_store"
    title: str | None = None
    text: str
    rating: int = Field(ge=1, le=5)
    date: datetime
    language: str = "en"


def is_valid_english_review(text: str, min_words: int = 8) -> bool:
    """
    Validates that a review text:
    1. Contains at least `min_words` words (default: 8).
    2. Contains no non-Latin script characters (Devanagari, Tamil, etc.).
    3. Is not Romanized Hindi / Hinglish.
    4. Is written primarily in the English language.
    """
    if not text or not text.strip():
        return False

    # 1. Non-Latin script rejection (Hindi, Telugu, Tamil, Bengali, etc.)
    if NON_LATIN_SCRIPT_PATTERN.search(text):
        return False

    # 2. Extract words
    tokens = re.findall(r"\b[a-zA-Z']+\b", text.lower())
    if len(tokens) < min_words:
        return False

    # 3. Hinglish rejection
    hinglish_count = sum(1 for w in tokens if w in HINGLISH_WORDS)
    english_count = sum(1 for w in tokens if w in COMMON_ENGLISH_WORDS)

    # If heavily dominated by Hinglish markers
    if hinglish_count >= 2 and hinglish_count >= english_count:
        return False

    # 4. English language presence check
    english_ratio = english_count / len(tokens)
    if english_ratio < 0.20:
        return False

    return True


def normalize(raw: dict[str, Any]) -> Review:
    """
    Normalizes a raw Play Store review dictionary into a validated Review model.
    """
    review_id = str(raw.get("reviewId") or raw.get("id", ""))
    content = str(raw.get("content") or raw.get("text", "")).strip()
    score = int(raw.get("score") if raw.get("score") is not None else raw.get("rating", 1))
    title = raw.get("replyContent") or raw.get("title")
    at = raw.get("at") or raw.get("date") or datetime.now()
    language = str(raw.get("language", "en"))

    return Review(
        id=review_id,
        source="play_store",
        title=title,
        text=content,
        rating=score,
        date=at,
        language=language,
    )


def deduplicate(reviews: list[Review]) -> list[Review]:
    """
    Deduplicates a list of Review objects preserving initial order.
    """
    seen: set[str] = set()
    unique_reviews: list[Review] = []
    for r in reviews:
        if r.id not in seen:
            seen.add(r.id)
            unique_reviews.append(r)
    return unique_reviews


def filter_reviews(reviews: list[Review], min_words: int = 8) -> list[Review]:
    """
    Filters reviews keeping only those with at least `min_words` words
    and written in the English language.
    """
    return [r for r in reviews if is_valid_english_review(r.text, min_words=min_words)]


def export_reviews_to_csv(reviews: list[Review], csv_path: Path) -> None:
    """
    Exports a list of Review objects to CSV format.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["id", "source", "rating", "date", "title", "language", "text"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in reviews:
            writer.writerow({
                "id": r.id,
                "source": r.source,
                "rating": r.rating,
                "date": r.date.isoformat() if hasattr(r.date, "isoformat") else str(r.date),
                "title": r.title or "",
                "language": r.language,
                "text": r.text,
            })
