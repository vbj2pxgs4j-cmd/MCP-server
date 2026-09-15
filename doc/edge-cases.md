# Edge Cases & Corner Scenarios — Weekly App Review Pulse via MCP

> Derived from [`implementation-plan.md`](./implementation-plan.md) and [`architecture.md`](./architecture.md).
> Organized by architectural layer. Each scenario includes the trigger condition, expected behavior, and recommended handling strategy.

---

## How to Use This Document

Each entry follows this format:

| Field      | Description                                                        |
| ---------- | ------------------------------------------------------------------ |
| **ID**     | Unique identifier for tracking in tests / issues                   |
| **Trigger**| The exact condition that causes this edge case                     |
| **Risk**   | 🔴 High / 🟡 Medium / 🟢 Low                                        |
| **Behavior**| What the system should do when this occurs                        |
| **Test**   | How to reproduce / write a unit test for this case                 |

---

## Layer 1 — Review Ingestion (Scraper)

### EC-S01 — No reviews in the configured time window

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `REVIEW_WINDOW_WEEKS=10` but the app has no reviews posted in the last 10 weeks (e.g., newly launched, or scrape window too narrow) |
| **Risk** | 🔴 High — pipeline halts with no output |
| **Behavior** | Scraper returns `[]`. System should **abort gracefully** with a clear message: `"No reviews found in the last N weeks. Skipping pulse generation."` Do NOT pass empty list to LangChain agent. |
| **Test** | Mock `reviews()` to return `[]`. Assert `load_reviews()` raises `NoReviewsError` or returns empty list. Assert orchestrator exits early without calling agent. |

```python
# Recommended guard in orchestrator.py
reviews = load_reviews()
if not reviews:
    print("⚠️  No reviews found. Skipping this week's pulse.")
    return
```

---

### EC-S02 — Scraper returns only non-English reviews

| Field    | Detail |
| -------- | ------ |
| **Trigger** | All fetched reviews are in Hindi, Telugu, or other regional languages (common for Groww's Indian user base) |
| **Risk** | 🔴 High — LLM may produce incorrect themes or fail structured output |
| **Behavior** | Filter reviews where `language != 'en'` OR pass all languages and instruct the LLM to process them. Recommended: filter to English only first; log how many were dropped. |
| **Test** | Inject 10 Hindi reviews + 2 English reviews. Assert `load_reviews()` returns only the 2 English ones (if language filtering is enabled). |

```python
# In normalizer.py
result = [r for r in result if r.get("language") == "en"]
if not result:
    # Fall back to all languages if English set is empty
    result = all_reviews
```

---

### EC-S03 — Play Store rate-limit / block (HTTP 429 or 403)

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Too many scrape requests in a short time; Google temporarily blocks the IP |
| **Risk** | 🔴 High — pipeline fails at ingestion with no data |
| **Behavior** | Retry up to 3 times with exponential backoff (1s → 2s → 4s). If all retries fail, fall back to the most recent `data/reviews/latest.json` cache. If no cache exists, abort with a clear error. |
| **Test** | Mock `reviews()` to raise `ConnectionError` 3 times then succeed. Assert retry count = 3 and final result is valid. Mock 3 failures + no cache → assert `ScraperError` is raised. |

```python
import time

def fetch_with_retry(app_id, weeks, retries=3, backoff=1.0):
    for attempt in range(retries):
        try:
            return fetch_reviews(app_id, weeks)
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))
```

---

### EC-S04 — Cache file is corrupt or invalid JSON

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `data/reviews/latest.json` exists but was truncated mid-write (e.g., process killed) |
| **Risk** | 🟡 Medium — loader crashes on `json.JSONDecodeError` |
| **Behavior** | Wrap cache read in `try/except json.JSONDecodeError`. On failure, delete the corrupt file and trigger a fresh scrape. |
| **Test** | Write `"{ broken json"` to `latest.json`. Assert loader performs a fresh scrape and overwrites the file. |

---

### EC-S05 — Duplicate reviews across scrape runs

| Field    | Detail |
| -------- | ------ |
| **Trigger** | A review fetched last week is fetched again this week (same `reviewId`) |
| **Risk** | 🟢 Low — inflates review count but doesn't break output |
| **Behavior** | Deduplicate by `Review.id` before persisting to cache and before passing to the agent. |
| **Test** | Create a list of 10 reviews with 3 duplicate IDs. Assert `deduplicate(reviews)` returns 7 unique reviews. |

```python
def deduplicate(reviews: list[Review]) -> list[Review]:
    seen = set()
    return [r for r in reviews if not (r.id in seen or seen.add(r.id))]
```

---

### EC-S06 — Review text is empty or very short (< 10 characters)

| Field    | Detail |
| -------- | ------ |
| **Trigger** | User posts a review with only emojis, a single word (e.g., "Good"), or an empty string |
| **Risk** | 🟢 Low — pollutes theme clustering with noise |
| **Behavior** | Filter out reviews where `len(text.strip()) < 10` during normalization. Log count of filtered reviews. |
| **Test** | Inject reviews with text `""`, `"👍"`, `"ok"`, and a valid 50-char review. Assert normalizer keeps only the 50-char one. |

---

### EC-S07 — `scraped_at` timestamp missing from cache

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Old cache file written without `scraped_at` field (schema migration scenario) |
| **Risk** | 🟢 Low — cache staleness check fails; may use indefinitely old data |
| **Behavior** | If `scraped_at` key is missing, treat cache as expired and trigger fresh scrape. |
| **Test** | Write cache JSON without `scraped_at`. Assert loader triggers fresh scrape. |

---

## Layer 2 — LangChain AI Agent

### EC-A01 — LLM returns malformed / non-JSON output from a tool

| Field    | Detail |
| -------- | ------ |
| **Trigger** | LLM ignores the structured JSON instruction and returns natural language text instead of `{"themes": [...]}` |
| **Risk** | 🔴 High — downstream pulse generator crashes on `KeyError` |
| **Behavior** | Wrap each tool's LLM call in `try/except`. If JSON parse fails, retry the tool call once with a stricter prompt: `"Respond ONLY with valid JSON. No prose."`. If second attempt fails, raise `ToolOutputError`. |
| **Test** | Mock LLM to return `"Here are the themes: ..."` (prose). Assert tool retries once. Mock second attempt to also fail → assert `ToolOutputError` is raised. |

```python
def _parse_json_output(raw: str, tool_name: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ToolOutputError(f"{tool_name} returned non-JSON: {raw[:100]}")
```

---

### EC-A02 — LLM invents or paraphrases user quotes

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `QuoteSelectorTool` LLM rewrites a user quote (e.g., "KYC stuck" → "The verification process was delayed") |
| **Risk** | 🔴 High — violates the hard requirement: *"verbatim snippets, no invented wording"* |
| **Behavior** | Post-process: for each returned quote, verify the exact string exists in the source reviews. If not found → reject that quote and request a replacement. |
| **Test** | Run `QuoteSelectorTool` with 20 known reviews. For each output quote, assert `quote.text in [r.text for r in reviews]`. |

```python
def validate_verbatim(quotes: list[dict], reviews: list[Review]) -> bool:
    review_texts = {r.text for r in reviews}
    return all(q["text"] in review_texts for q in quotes)
```

---

### EC-A03 — LLM produces more than 5 themes

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Despite `"at most 5"` in the prompt, LLM returns 6–8 theme objects |
| **Risk** | 🟡 Medium — pulse note exceeds one-page format |
| **Behavior** | Hard-cap at 5 themes: `themes = themes[:5]`. Log a warning. The top 3 are selected for the pulse anyway. |
| **Test** | Mock `ThemeClustererTool` to return 7 themes. Assert `run_analysis()` output has `len(themes) <= 5`. |

---

### EC-A04 — LLM produces fewer than 3 quotes or 3 actions

| Field    | Detail |
| -------- | ------ |
| **Trigger** | LLM returns only 1–2 quotes or 1–2 action ideas (underperforms on count) |
| **Risk** | 🟡 Medium — pulse note is incomplete; delivery looks unprofessional |
| **Behavior** | Validate count after tool call. If `len(quotes) < 3`, retry `QuoteSelectorTool` once. If still short, pad with a note: `"[Insufficient distinct quotes available this week]"`. Same for actions. |
| **Test** | Mock `QuoteSelectorTool` to return 1 quote. Assert retry is triggered. Assert final output has at least a placeholder if still short. |

---

### EC-A05 — Groq API rate limit / timeout

| Field    | Detail |
| -------- | ------ |
| **Trigger** | LangChain tool call hits Groq's rate limit (HTTP 429) or the request times out after 30s |
| **Risk** | 🔴 High — agent crashes mid-execution |
| **Behavior** | Set `ChatGroq(request_timeout=60)`. LangChain's built-in retry handles transient 429s. If all retries exhausted, catch `RateLimitError` and fall back to OpenAI (`ChatOpenAI`) if `OPENAI_API_KEY` is configured. |
| **Test** | Mock Groq to raise `RateLimitError`. Assert system falls back to OpenAI client. Assert if both fail → raises `LLMUnavailableError`. |

```python
# In executor.py
try:
    llm = ChatGroq(api_key=config.LLM_API_KEY, model=config.LLM_MODEL)
except Exception:
    if config.OPENAI_API_KEY:
        llm = ChatOpenAI(api_key=config.OPENAI_API_KEY, model="gpt-4o-mini")
    else:
        raise LLMUnavailableError("All LLM providers failed.")
```

---

### EC-A06 — Agent enters infinite tool-call loop

| Field    | Detail |
| -------- | ------ |
| **Trigger** | LangChain `AgentExecutor` keeps calling the same tool repeatedly (e.g., LLM keeps trying `ThemeClustererTool` and never proceeds) |
| **Risk** | 🟡 Medium — burns API tokens and hangs |
| **Behavior** | Set `AgentExecutor(max_iterations=10)` to cap tool call attempts. If exceeded, `AgentExecutor` raises `OutputParserException` — catch and raise `AgentLoopError`. |
| **Test** | Mock LLM to always return `"Call ThemeClustererTool again"`. Assert agent stops after `max_iterations=10` and raises `AgentLoopError`. |

---

### EC-A07 — All reviews belong to only 1 theme

| Field    | Detail |
| -------- | ------ |
| **Trigger** | A specific week's reviews are overwhelmingly about one topic (e.g., a major outage week) |
| **Risk** | 🟢 Low — system still works; pulse is simply less diverse |
| **Behavior** | Accept 1-theme output. Log `"Warning: all reviews clustered into 1 theme."` Pulse generation proceeds normally with `top_themes[:1]`. Quotes and actions are drawn from that single theme. |
| **Test** | Pass 20 reviews all about "app crash". Assert `ThemeClustererTool` returns 1 theme. Assert pulse renders with 1 theme and correct quotes from that theme. |

---

### EC-A08 — Review batch too large for LLM context window

| Field    | Detail |
| -------- | ------ |
| **Trigger** | 500+ reviews scraped, serialized JSON exceeds the LLM's context limit (~8K tokens for some models) |
| **Risk** | 🟡 Medium — LLM returns a context length error |
| **Behavior** | Before passing to agent, truncate to the most recent `MAX_REVIEWS = 200` reviews. Alternatively, chunk into batches of 50, cluster each batch, then merge themes across batches. |
| **Test** | Create 250 mock reviews. Assert input to `ThemeClustererTool` has `len <= 200`. |

```python
MAX_REVIEWS_PER_AGENT_CALL = 200

reviews_for_agent = sorted(reviews, key=lambda r: r.date, reverse=True)[:MAX_REVIEWS_PER_AGENT_CALL]
```

---

## Layer 3 — Pulse Generation

### EC-P01 — Jinja2 template variable is None or missing

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `agent_output["quotes"]` or `agent_output["actions"]` is `None` (tool failed silently) |
| **Risk** | 🟡 Medium — Jinja2 renders `None` literally or raises `UndefinedError` |
| **Behavior** | Validate `agent_output` schema with Pydantic before passing to template. If any required key is missing, raise `PulseGenerationError` with detail on what's missing. |
| **Test** | Call `generate_pulse({}, reviews)`. Assert `PulseGenerationError` is raised, not a Jinja2 traceback. |

---

### EC-P02 — Quote text contains Markdown-breaking characters

| Field    | Detail |
| -------- | ------ |
| **Trigger** | A verbatim quote contains `**`, `_`, `#`, `>`, or backticks that break Markdown rendering in Google Docs |
| **Risk** | 🟢 Low — visual corruption in the rendered Doc |
| **Behavior** | Escape Markdown special characters in `quote.text` before injecting into the template. Do NOT alter the raw quote — apply escaping only at render time. |
| **Test** | Pass a quote `"app is **broken** and #bad"`. Assert rendered Markdown wraps it in a blockquote correctly without formatting breakage. |

---

### EC-P03 — Week date range spans two months

| Field    | Detail |
| -------- | ------ |
| **Trigger** | The weekly window crosses a month boundary (e.g., Sep 28 – Oct 4) |
| **Risk** | 🟢 Low — date display looks awkward |
| **Behavior** | Format dates as `"Sep 28 – Oct 4, 2026"` (short month names). Already handled by `strftime("%b %d, %Y")` — verify format string handles different year end-of-year edge case too. |
| **Test** | Set `date.today()` to `2026-01-03`. Assert pulse header reads `"Dec 27, 2025 – Jan 3, 2026"`. |

---

### EC-P04 — HTML template generates email body too large for Gmail

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Extremely long theme descriptions + quotes push HTML body over Gmail's size limit (~25 MB, but drafts can fail at ~1 MB via API) |
| **Risk** | 🟢 Low — highly unlikely at current data volume |
| **Behavior** | Truncate each theme description to 500 chars and each quote to 300 chars in the HTML template. Full content is always in the Google Doc. |
| **Test** | Generate pulse with theme descriptions of 2000 chars. Assert HTML output `len < 50_000` bytes. |

---

## Layer 4 — MCP Delivery (Google Docs + Gmail)

### EC-D01 — MCP server process fails to start

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `npx @anthropic/google-docs-mcp` fails because Node.js is not installed, npm registry is unreachable, or the package name changed |
| **Risk** | 🔴 High — delivery fails entirely |
| **Behavior** | Catch `MCPConnectionError` on startup. Print actionable error: `"MCP server failed to start. Ensure Node.js ≥ 18 is installed and npm registry is accessible."`. Save pulse markdown to `data/pulse_draft_YYYYMMDD.md` as a local fallback so the content is not lost. |
| **Test** | Mock MCP client to raise `ConnectionError` on `__aenter__`. Assert pulse markdown is written to fallback file. |

---

### EC-D02 — Google OAuth token expired or revoked

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `GOOGLE_REFRESH_TOKEN` in `.env` has expired or been revoked by the user in Google Account settings |
| **Risk** | 🔴 High — all MCP tool calls fail with `401 Unauthorized` |
| **Behavior** | Catch `AuthenticationError` from MCP server. Print: `"Google OAuth token is invalid. Re-authenticate and update GOOGLE_REFRESH_TOKEN in .env."`. Exit with code `1`. |
| **Test** | Mock MCP tool call to raise `AuthenticationError`. Assert process exits with code `1` and prints re-authentication instructions. |

---

### EC-D03 — Google Docs MCP tool creates duplicate documents

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Orchestrator is run twice in the same week (e.g., testing or accidental re-run); two identical pulse docs are created |
| **Risk** | 🟡 Medium — clutters Google Drive |
| **Behavior** | Before calling `create_document`, search for an existing doc with the same weekly title using `search_documents(title=pulse_title)`. If found, call `update_document` instead of `create_document`. |
| **Test** | Mock MCP `search_documents` to return an existing doc ID. Assert `update_document` is called, NOT `create_document`. |

```python
existing = await search_documents(title=title)
if existing:
    await update_document(doc_id=existing[0]["id"], content=markdown)
else:
    await create_document(title=title, content=markdown)
```

---

### EC-D04 — Gmail MCP creates draft but draft is not visible

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `create_draft` returns a `draft_id` but the draft does not appear in Gmail Drafts (a race condition or eventual consistency delay) |
| **Risk** | 🟢 Low — data integrity issue, not a crash |
| **Behavior** | After `create_draft`, call `get_draft(draft_id)` to confirm it exists. If not found after 3s, log a warning but do not fail the entire run. |
| **Test** | Mock `create_draft` to return `draft_id`. Mock `get_draft` to return `None` on first call, then the draft on retry. Assert warning is logged on first miss. |

---

### EC-D05 — MCP tool call times out

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Google Docs or Gmail MCP tool call hangs indefinitely (network issue, Google service degradation) |
| **Risk** | 🔴 High — orchestrator hangs forever |
| **Behavior** | Wrap all MCP calls in `asyncio.wait_for(coro, timeout=30)`. On `asyncio.TimeoutError`, retry once after 5s. If still timing out, save local fallback and exit with error. |
| **Test** | Mock MCP coroutine to `asyncio.sleep(100)`. Assert `TimeoutError` is caught within 30s and retry is attempted. |

```python
try:
    doc_url = await asyncio.wait_for(publish_to_docs(markdown, title), timeout=30)
except asyncio.TimeoutError:
    print("⏱️  MCP Docs call timed out. Saving local fallback.")
    save_local_fallback(markdown)
```

---

### EC-D06 — Network connectivity lost mid-pipeline

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Internet disconnects after scraping succeeds but before MCP delivery |
| **Risk** | 🟡 Medium — partial run; reviews and pulse generated but not delivered |
| **Behavior** | Persist the generated pulse Markdown to `data/pulse_draft_YYYYMMDD.md` immediately after Phase 4 (before Phase 5). On next run, check for an un-delivered draft from the same week and attempt delivery without re-scraping or re-running the agent. |
| **Test** | Simulate network failure by mocking MCP call. Assert `data/pulse_draft_*.md` exists with correct content. On second run with network restored, assert delivery succeeds without hitting LLM again. |

---

## Cross-Layer / Orchestration Edge Cases

### EC-O01 — Environment variable missing at startup

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `.env` is missing `LLM_API_KEY` or `PULSE_RECIPIENT_EMAIL` |
| **Risk** | 🔴 High — cryptic `NoneType` errors deep in the pipeline |
| **Behavior** | Validate all required env vars in `src/config.py` at import time. If any are missing, raise `ConfigurationError` immediately with a list of missing vars. Do NOT wait until the var is actually used. |
| **Test** | Unset `LLM_API_KEY` from env. Assert `import src.config` raises `ConfigurationError: Missing required env vars: LLM_API_KEY`. |

```python
REQUIRED_VARS = ["LLM_API_KEY", "PULSE_RECIPIENT_EMAIL"]

missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    raise ConfigurationError(f"Missing required env vars: {', '.join(missing)}")
```

---

### EC-O02 — Orchestrator run during weekend / public holiday (no new reviews)

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Cron fires on a Monday but the week's window has unusually low review volume (< 5 reviews) |
| **Risk** | 🟡 Medium — pulse with 5 reviews is statistically unreliable for theming |
| **Behavior** | Add `MIN_REVIEWS_THRESHOLD = 20`. If `len(reviews) < 20`, log a warning and either skip the run or produce a pulse with a disclaimer note: `"⚠️ Low review volume this week (N reviews). Themes may be less representative."` |
| **Test** | Pass 4 reviews. Assert orchestrator either skips or appends disclaimer to pulse output. |

---

### EC-O03 — Concurrent runs (two cron jobs fire simultaneously)

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Misconfigured cron fires twice or two users trigger manual runs at the same time |
| **Risk** | 🟡 Medium — race condition on cache file write; duplicate Google Docs created |
| **Behavior** | Use a `.lock` file in `data/` to prevent concurrent runs. If lock exists, second run prints `"Another run is in progress. Exiting."` and exits with code `0`. Lock is deleted on completion or crash. |
| **Test** | Mock a pre-existing `.lock` file. Assert second orchestrator invocation exits immediately without calling any tools. |

```python
LOCK_FILE = Path("data/.pulse.lock")

if LOCK_FILE.exists():
    print("⚠️  Another run is in progress. Exiting.")
    sys.exit(0)

LOCK_FILE.touch()
try:
    await run()
finally:
    LOCK_FILE.unlink(missing_ok=True)
```

---

### EC-O04 — Target app ID changed or app delisted

| Field    | Detail |
| -------- | ------ |
| **Trigger** | `com.nextbillion.groww` is renamed, delisted, or replaced by a new app ID on the Play Store |
| **Risk** | 🔴 High — scraper returns `AppNotFoundException` |
| **Behavior** | Catch `AppNotFoundException` from `google_play_scraper`. Print: `"App ID {TARGET_APP_ID} not found on Play Store. Verify the app ID in .env."` Exit with code `1`. |
| **Test** | Mock `reviews()` to raise `AppNotFoundException`. Assert process exits with code `1` and prints actionable message. |

---

### EC-O05 — First-ever run (cold start, no cache, no prior data)

| Field    | Detail |
| -------- | ------ |
| **Trigger** | Running the system for the very first time; `data/reviews/` directory is empty |
| **Risk** | 🟢 Low — expected scenario, should be handled gracefully |
| **Behavior** | Scraper runs a fresh fetch (no cache to fall back to). Ensure `data/reviews/` directory is created automatically if it doesn't exist. Log `"Cold start — fetching reviews for the first time."` |
| **Test** | Delete `data/reviews/` directory. Run `load_reviews()`. Assert directory is created and reviews are fetched. |

```python
CACHE_DIR = Path("data/reviews")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
```

---

## Summary: Edge Case Matrix

| ID     | Layer     | Risk  | Type                    | Handling Strategy               |
| ------ | --------- | ----- | ----------------------- | ------------------------------- |
| EC-S01 | Scraper   | 🔴   | Empty result set        | Abort early with clear message  |
| EC-S02 | Scraper   | 🔴   | Language filtering      | Filter to English; fallback all |
| EC-S03 | Scraper   | 🔴   | HTTP 429 / block        | Retry + backoff + cache fallback|
| EC-S04 | Scraper   | 🟡   | Corrupt cache           | Delete + re-scrape              |
| EC-S05 | Scraper   | 🟢   | Duplicate reviews       | Deduplicate by ID               |
| EC-S06 | Scraper   | 🟢   | Empty/short text        | Filter at normalization         |
| EC-S07 | Scraper   | 🟢   | Missing cache timestamp | Treat as expired                |
| EC-A01 | Agent     | 🔴   | Malformed JSON output   | Retry with strict prompt        |
| EC-A02 | Agent     | 🔴   | Paraphrased quotes      | Post-validate verbatim match    |
| EC-A03 | Agent     | 🟡   | Too many themes         | Hard-cap at 5                   |
| EC-A04 | Agent     | 🟡   | Too few quotes/actions  | Retry; pad with placeholder     |
| EC-A05 | Agent     | 🔴   | LLM rate limit          | Retry; fallback to OpenAI       |
| EC-A06 | Agent     | 🟡   | Infinite tool loop      | `max_iterations=10`             |
| EC-A07 | Agent     | 🟢   | Single-theme week       | Accept; log warning             |
| EC-A08 | Agent     | 🟡   | Context window overflow | Truncate to 200 reviews         |
| EC-P01 | Pulse     | 🟡   | Missing template vars   | Pydantic validation pre-render  |
| EC-P02 | Pulse     | 🟢   | Markdown special chars  | Escape at render time           |
| EC-P03 | Pulse     | 🟢   | Month-boundary dates    | Verify `strftime` format        |
| EC-P04 | Pulse     | 🟢   | HTML body too large     | Truncate descriptions/quotes    |
| EC-D01 | Delivery  | 🔴   | MCP server won't start  | Local fallback file             |
| EC-D02 | Delivery  | 🔴   | OAuth token expired     | Exit with re-auth instructions  |
| EC-D03 | Delivery  | 🟡   | Duplicate Google Docs   | Search-then-update pattern      |
| EC-D04 | Delivery  | 🟢   | Draft not visible       | Confirm via `get_draft`         |
| EC-D05 | Delivery  | 🔴   | MCP call timeout        | `asyncio.wait_for(timeout=30)`  |
| EC-D06 | Delivery  | 🟡   | Mid-pipeline disconnect | Persist pulse before delivery   |
| EC-O01 | Orch.     | 🔴   | Missing env vars        | Fail-fast at config import      |
| EC-O02 | Orch.     | 🟡   | Low review volume       | Threshold check + disclaimer    |
| EC-O03 | Orch.     | 🟡   | Concurrent runs         | Lock file                       |
| EC-O04 | Orch.     | 🔴   | App ID not found        | Exit with actionable message    |
| EC-O05 | Orch.     | 🟢   | Cold start / no cache   | Auto-create dirs; fresh scrape  |
