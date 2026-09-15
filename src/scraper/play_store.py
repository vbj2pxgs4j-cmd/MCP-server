import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from google_play_scraper import Sort, reviews

logger = logging.getLogger(__name__)


def _make_comparable(dt: datetime, reference_dt: datetime) -> tuple[datetime, datetime]:
    """Ensures both datetimes have matching timezone awareness for comparison."""
    if dt.tzinfo is None and reference_dt.tzinfo is not None:
        dt = dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo is not None and reference_dt.tzinfo is None:
        reference_dt = reference_dt.replace(tzinfo=timezone.utc)
    return dt, reference_dt


def fetch_reviews(
    app_id: str,
    weeks: int = 8,
    max_reviews: int = 1500,
    page_size: int = 200,
    retries: int = 3,
    backoff: float = 1.0,
) -> list[dict[str, Any]]:
    """
    Fetches Play Store reviews from the last `weeks` weeks for the given `app_id`
    using pagination until the date cutoff or `max_reviews` is reached.
    Retries up to `retries` times on connection errors.
    """
    cutoff = datetime.now() - timedelta(weeks=weeks)
    collected_reviews: list[dict[str, Any]] = []
    continuation_token = None
    reached_cutoff = False

    logger.info("Starting review fetch for %s (weeks=%d, cutoff=%s)", app_id, weeks, cutoff)

    while not reached_cutoff and len(collected_reviews) < max_reviews:
        batch_success = False
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                if continuation_token is None:
                    batch, continuation_token = reviews(
                        app_id,
                        lang="en",
                        country="in",
                        sort=Sort.NEWEST,
                        count=page_size,
                    )
                else:
                    batch, continuation_token = reviews(
                        app_id,
                        continuation_token=continuation_token,
                    )
                batch_success = True
                break
            except Exception as exc:
                last_error = exc
                logger.warning("Scrape attempt %d failed: %s", attempt + 1, exc)
                if attempt < retries - 1:
                    time.sleep(backoff * (2 ** attempt))

        if not batch_success:
            if collected_reviews:
                logger.warning("Scrape interrupted by error, returning %d collected reviews", len(collected_reviews))
                break
            if last_error:
                raise last_error
            break

        if not batch:
            logger.info("No more reviews returned from Play Store.")
            break

        for r in batch:
            review_date = r.get("at")
            if isinstance(review_date, datetime):
                r_dt, ref_cutoff = _make_comparable(review_date, cutoff)
                if r_dt >= ref_cutoff:
                    collected_reviews.append(r)
                else:
                    reached_cutoff = True
                    break
            else:
                collected_reviews.append(r)

            if len(collected_reviews) >= max_reviews:
                break

        logger.info("Fetched batch of %d reviews. Total within window: %d", len(batch), len(collected_reviews))

        if not continuation_token or reached_cutoff:
            break

    logger.info("Completed review ingestion: %d reviews within last %d weeks.", len(collected_reviews), weeks)
    return collected_reviews
