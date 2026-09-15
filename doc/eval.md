# Evaluation Rubric — Weekly App Review Pulse via MCP

> Derived from [`implementation-plan.md`](./implementation-plan.md).
> This document defines how the project is graded — phase by phase, criteria by criteria.
> Use this as a self-assessment checklist before submission and as a reviewer's scoring guide.

---

## Scoring Overview

| Category                        | Max Points | Weight  |
| ------------------------------- | ---------- | ------- |
| Phase 1 — Project Setup         | 10         | 6%      |
| Phase 2 — Review Ingestion      | 20         | 12%     |
| Phase 3 — LangChain AI Agent    | 40         | 24%     |
| Phase 4 — Pulse Generation      | 20         | 12%     |
| Phase 5 — MCP Delivery          | 40         | 24%     |
| Code Quality & Design           | 15         | 9%      |
| Testing & Reliability           | 15         | 9%      |
| Documentation                   | 5          | 3%      |
| **TOTAL**                       | **165**    | **100%**|

> [!IMPORTANT]
> **Phase 5 (MCP Delivery) and Phase 3 (LangChain Agent) together account for 48% of the total score.** These are the two hardest and most differentiating components.

---

## Grading Scale

| Score (% of total) | Grade | Descriptor                                      |
| ------------------- | ----- | ----------------------------------------------- |
| 90 – 100%           | A+    | Exceptional — all criteria met, polished output  |
| 80 – 89%            | A     | Strong — core pipeline fully works end-to-end    |
| 70 – 79%            | B     | Good — most phases complete, minor gaps in delivery |
| 60 – 69%            | C     | Adequate — scraping + agent work; delivery partial |
| 50 – 59%            | D     | Partial — at least scraping and clustering work  |
| < 50%               | F     | Incomplete — core pipeline cannot run            |

---

## Phase 1 — Project Setup & Scaffolding (10 pts)

| #   | Criterion                                                                    | Points | How to Verify                                                      |
| --- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 1.1 | All required directories exist (`src/`, `agent/tools/`, `pulse/templates/`, `tests/`, `data/reviews/`, `config/`) | 2 | `ls -R src/ config/ tests/ data/` |
| 1.2 | `requirements.txt` lists all required packages (`langchain`, `langchain-groq`, `google-play-scraper`, `jinja2`, `pydantic>=2.0`, `python-dotenv`, `pytest`) | 3 | `pip install -r requirements.txt` succeeds with no errors |
| 1.3 | `.env.example` committed with all 8 required keys; `.env` not committed | 2 | `git show HEAD:.env.example` works; `git show HEAD:.env` fails |
| 1.4 | `src/config.py` loads env vars and exposes typed values | 2 | `python -c "from src.config import TARGET_APP_ID; print(TARGET_APP_ID)"` prints `com.nextbillion.groww` |
| 1.5 | `config/mcp_config.json` exists with both `google-docs` and `gmail` server entries | 1 | `cat config/mcp_config.json` shows both servers |

**Automatic 0 for this phase if:** any `__init__.py` is missing, making the package unimportable.

---

## Phase 2 — Review Ingestion (20 pts)

| #   | Criterion                                                                    | Points | How to Verify                                                      |
| --- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 2.1 | `fetch_reviews()` fetches real reviews from Play Store for `com.nextbillion.groww` | 4 | Run with live network; assert `len(result) > 0` |
| 2.2 | Reviews are filtered to the configured time window (≥ 8 weeks)              | 3 | Set `REVIEW_WINDOW_WEEKS=8`; assert no review's date is older than 8 weeks |
| 2.3 | `Review` Pydantic model has all required fields: `id`, `text`, `rating`, `date`, `source` | 3 | `Review(**mock_raw)` validates without error |
| 2.4 | `normalize()` correctly maps raw Play Store dict to `Review` model           | 3 | Unit test with known input/output pair |
| 2.5 | Cache is written to `data/reviews/latest.json` with `scraped_at` timestamp   | 3 | File exists after first run; contains `"scraped_at"` key |
| 2.6 | Cache is correctly loaded on second run (no re-scrape within 7 days)         | 2 | Second run is significantly faster; scraper mock not called |
| 2.7 | `test_scraper.py` passes (`pytest tests/test_scraper.py -v`)                | 2 | All tests green |

**Automatic deduction (−5):** If real Play Store reviews cannot be fetched (wrong app ID, no pagination).

---

## Phase 3 — LangChain AI Agent (40 pts)

This is the core technical component. Evaluated across tool design, agent wiring, output correctness, and prompt quality.

### 3A — Tool Implementation (20 pts)

| #    | Criterion                                                                    | Points | How to Verify                                                      |
| ---- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 3A.1 | `ThemeClustererTool` extends `BaseTool`, has correct `name` + `description`  | 3 | `tool.name == "ThemeClustererTool"`; `tool.description` is non-empty and descriptive |
| 3A.2 | `ThemeClustererTool._run()` returns valid JSON with `{"themes": [...]}`      | 4 | Run with 20 sample reviews; `json.loads(output)["themes"]` succeeds |
| 3A.3 | `QuoteSelectorTool._run()` returns exactly 3 quotes, all verbatim           | 5 | Each returned `quote.text` must exist as a substring of an input review's `text` |
| 3A.4 | `ActionGeneratorTool._run()` returns exactly 3 actions with `title` + `description` | 4 | `json.loads(output)["actions"]` has `len == 3`; each has `title` and `description` |
| 3A.5 | All tools return JSON (not natural language prose)                           | 4 | Mock 5 runs; `json.loads()` succeeds every time |

### 3B — Agent Wiring (12 pts)

| #    | Criterion                                                                    | Points | How to Verify                                                      |
| ---- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 3B.1 | `build_agent_executor()` creates a valid `AgentExecutor` with all 3 tools    | 3 | `agent_executor.tools` has length 3 |
| 3B.2 | LLM is initialized with `temperature=0.3` and correct model                 | 2 | Inspect `llm.temperature` and `llm.model_name` |
| 3B.3 | `AgentExecutor` has `max_iterations` set (prevents infinite loops)           | 2 | `agent_executor.max_iterations <= 15` |
| 3B.4 | `run_analysis(reviews)` returns dict with keys `themes`, `quotes`, `actions` | 3 | Assert `set(output.keys()) == {"themes", "quotes", "actions"}` |
| 3B.5 | Agent run is visible in console with `verbose=True`                          | 2 | Run and observe tool call logs in stdout |

### 3C — Output Correctness (8 pts)

| #    | Criterion                                                                    | Points | How to Verify                                                      |
| ---- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 3C.1 | Output has ≤ 5 themes                                                        | 2 | `len(output["themes"]) <= 5` |
| 3C.2 | Output has exactly 3 quotes                                                  | 2 | `len(output["quotes"]) == 3` |
| 3C.3 | Output has exactly 3 actions                                                 | 2 | `len(output["actions"]) == 3` |
| 3C.4 | `test_agent.py` passes (`pytest tests/test_agent.py -v`)                    | 2 | All tests green |

> [!CAUTION]
> **Verbatim quote check is the hardest single criterion in the project (3A.3, 5 pts).** Quotes must match source review text exactly — not paraphrased, summarized, or partially reworded. This will be verified by checking the returned quote string against the raw review corpus.

---

## Phase 4 — Pulse Generation (20 pts)

| #   | Criterion                                                                    | Points | How to Verify                                                      |
| --- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 4.1 | `pulse.md.j2` Jinja2 template exists and renders without error               | 3 | `env.get_template("pulse.md.j2").render(**mock_context)` succeeds |
| 4.2 | `pulse.html.j2` exists with inline styles (Gmail-compatible)                 | 2 | File exists; `<style>` or `style=` attributes visible; no external CSS links |
| 4.3 | Rendered Markdown includes all 3 required sections: Top Themes, User Quotes, Action Ideas | 5 | String contains `"Top Themes"`, `"What Users Are Saying"`, `"Action Ideas"` |
| 4.4 | Week date range is correct (today − 7 days to today)                         | 3 | `"week_start"` in pulse is 7 days before `"week_end"` |
| 4.5 | `review_count` in pulse matches number of reviews passed to `generate_pulse()` | 2 | `pulse_markdown.count(str(len(reviews))) > 0` |
| 4.6 | HTML output is non-empty and contains all 3 sections                         | 3 | `len(pulse["html"]) > 500`; sections present |
| 4.7 | `test_pulse.py` passes (`pytest tests/test_pulse.py -v`)                    | 2 | All tests green |

---

## Phase 5 — MCP Delivery (40 pts)

This is the highest-stakes phase — it proves integration works end-to-end with real Google Workspace via MCP.

### 5A — Google Docs (18 pts)

| #    | Criterion                                                                    | Points | How to Verify                                                      |
| ---- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 5A.1 | `mcp_config.json` correctly references the Google Docs MCP server            | 2 | Config parses; server command is valid `npx` invocation |
| 5A.2 | `publish_to_docs()` uses MCP tool call (NOT direct Google Docs API)          | 5 | Code review: no `googleapiclient` or `requests` to `docs.googleapis.com` |
| 5A.3 | A real Google Doc is created when the pipeline runs                          | 5 | `doc_url` is a valid `https://docs.google.com/document/d/...` URL that opens |
| 5A.4 | The Google Doc contains the correct pulse content (themes, quotes, actions)  | 4 | Open doc in browser; all 3 sections visible |
| 5A.5 | Duplicate run calls `update_document` instead of creating a new doc          | 2 | Second run within same week: same doc URL returned, not a new one |

### 5B — Gmail (15 pts)

| #    | Criterion                                                                    | Points | How to Verify                                                      |
| ---- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 5B.1 | `create_draft()` uses MCP tool call (NOT direct Gmail API)                   | 5 | Code review: no `gmail_v1` or direct OAuth client; uses MCP session |
| 5B.2 | A real Gmail draft is created in the configured account's Drafts folder      | 4 | Open Gmail; draft visible with correct subject `"Weekly App Review Pulse"` |
| 5B.3 | Draft body contains the Google Doc link                                      | 3 | Open draft; `doc_url` is clickable in the email body |
| 5B.4 | Draft is addressed to `PULSE_RECIPIENT_EMAIL` (from `.env`)                  | 3 | Draft `To:` field matches `.env` value |

### 5C — End-to-End Orchestration (7 pts)

| #    | Criterion                                                                    | Points | How to Verify                                                      |
| ---- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| 5C.1 | `python -m src.orchestrator` runs end-to-end without manual intervention     | 3 | Single command completes; prints ✅ with doc URL and draft ID |
| 5C.2 | `test_delivery.py` passes (`pytest tests/test_delivery.py -v`)              | 2 | All tests green |
| 5C.3 | Orchestrator prints step-by-step progress (Steps 1/4 → 4/4)                 | 2 | Console output shows all 4 steps |

> [!CAUTION]
> **MCP-first is a hard requirement.** Any use of `google-api-python-client`, `requests` to Google APIs, or manual OAuth token exchange for Docs or Gmail will result in a **mandatory −15 point deduction** regardless of whether the output looks correct.

---

## Code Quality & Design (15 pts)

| #   | Criterion                                                                    | Points | How to Verify                                                      |
| --- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| Q.1 | No secrets committed to git (`.env` in `.gitignore`; no hardcoded API keys) | 3 | `git grep "sk-\|gsk_\|AIza"` returns empty |
| Q.2 | `src/config.py` validates required env vars at import time (fail-fast)       | 3 | Removing `LLM_API_KEY` from env causes immediate `ConfigurationError`, not a later crash |
| Q.3 | Error handling: scraper, LLM, MCP failures each have distinct exception types and messages | 3 | Code review; each layer has meaningful `try/except` blocks |
| Q.4 | No raw `print()` used for errors — uses `logging` or structured error messages | 2 | `grep -r "^print" src/` returns only progress-log prints, not exception handling |
| Q.5 | `Review` schema uses Pydantic v2; `agent_output` validated before rendering  | 2 | `Review.model_validate(...)` used; no raw dict access without validation |
| Q.6 | Async/await used correctly in delivery layer (`asyncio.wait_for` + timeouts) | 2 | `mcp_docs.py` and `mcp_gmail.py` are `async def`; timeouts present |

---

## Testing & Reliability (15 pts)

| #   | Criterion                                                                    | Points | How to Verify                                                      |
| --- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| T.1 | All 4 test files exist: `test_scraper.py`, `test_agent.py`, `test_pulse.py`, `test_delivery.py` | 2 | `ls tests/` |
| T.2 | `pytest tests/ -v` passes with 0 failures                                    | 5 | Run command; check exit code `0` |
| T.3 | LLM calls are mocked in tests (no real API calls during test suite)           | 3 | Tests run without `LLM_API_KEY` set; no network calls |
| T.4 | MCP tool calls are mocked in `test_delivery.py`                               | 2 | Tests run without Google credentials; all pass |
| T.5 | At least 15 total test cases across all 4 files                               | 3 | `pytest tests/ --collect-only | grep "test session"` shows ≥ 15 |

---

## Documentation (5 pts)

| #   | Criterion                                                                    | Points | How to Verify                                                      |
| --- | ---------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| D.1 | `README.md` exists with: setup steps, `.env` configuration, how to run      | 3 | A new developer can follow README to run the project in < 15 min |
| D.2 | `doc/` contains all 5 required docs: `problemStatement.md`, `architecture.md`, `implementation-plan.md`, `edge-cases.md`, `eval.md` | 2 | `ls doc/` |

---

## Bonus Points (up to +10)

These are awarded for going beyond the base requirements.

| #   | Bonus Criterion                                                              | Points |
| --- | ---------------------------------------------------------------------------- | ------ |
| B.1 | **LangSmith tracing** configured and a trace URL is printed after each run   | +3     |
| B.2 | **Lock file guard** implemented to prevent concurrent runs (EC-O03)          | +2     |
| B.3 | **Search-before-create** logic in `mcp_docs.py` (no duplicate Docs per week) | +2     |
| B.4 | **Verbatim quote validator** as a post-processing step (EC-A02)              | +3     |

---

## Penalty Deductions

| #   | Violation                                                                     | Deduction |
| --- | ----------------------------------------------------------------------------- | --------- |
| P.1 | Direct Google API calls used for Docs or Gmail (not MCP)                      | −15       |
| P.2 | Quotes in pulse are paraphrased (verified against source review corpus)        | −10       |
| P.3 | Secrets committed to git (API keys, OAuth tokens in any file)                 | −10       |
| P.4 | `pytest tests/ -v` fails with errors (not skips)                              | −5        |
| P.5 | `python -m src.orchestrator` crashes before producing any output              | −10       |
| P.6 | No `.gitignore` or `.env` not gitignored                                      | −5        |

---

## Evaluator's Checklist — End-to-End Verification Run

Follow these steps in order to evaluate the complete submission:

```bash
# 1. Clone and setup
git clone <repo-url> && cd MCP-server
pip install -r requirements.txt
cp .env.example .env
# Fill in .env with real credentials

# 2. Phase 1 check
python -c "from src.config import TARGET_APP_ID; print(TARGET_APP_ID)"

# 3. Phase 2 check
python -c "from src.scraper import load_reviews; r = load_reviews(); print(f'{len(r)} reviews loaded')"

# 4. Phase 3 check (requires LLM_API_KEY)
python -c "
from src.scraper import load_reviews
from src.agent import run_analysis
reviews = load_reviews()
out = run_analysis(reviews[:20])
print('Themes:', len(out['themes']))
print('Quotes:', len(out['quotes']))
print('Actions:', len(out['actions']))
"

# 5. Phase 4 check
python -c "
from src.pulse.generator import generate_pulse
mock_output = {
    'themes': [{'name': 'KYC', 'description': 'KYC issues'}] * 3,
    'quotes': [{'theme': 'KYC', 'text': 'KYC stuck', 'rating': 1}] * 3,
    'actions': [{'title': 'Fix KYC', 'description': 'Speed up KYC'}] * 3,
}
pulse = generate_pulse(mock_output, [])
print('Markdown length:', len(pulse['markdown']))
print('HTML length:', len(pulse['html']))
"

# 6. Full test suite
pytest tests/ -v

# 7. Phase 5 — full end-to-end (requires Google credentials in .env)
python -m src.orchestrator
```

**Expected final output:**
```
🔍 Step 1/4 — Fetching Play Store reviews...
🤖 Step 2/4 — Running LangChain agent on N reviews...
📝 Step 3/4 — Generating weekly pulse note...
📤 Step 4/4 — Delivering via MCP...

✅ Done!
   Google Doc : https://docs.google.com/document/d/...
   Gmail Draft: <draft_id>
```

---

## Score Sheet Template

```
Submission: ___________________   Date: ___________   Evaluator: ___________

PHASE 1  — Project Setup         _____ / 10
PHASE 2  — Review Ingestion      _____ / 20
PHASE 3  — LangChain AI Agent    _____ / 40
  3A  Tool Implementation          _____ / 20
  3B  Agent Wiring                 _____ / 12
  3C  Output Correctness           _____ / 8
PHASE 4  — Pulse Generation      _____ / 20
PHASE 5  — MCP Delivery          _____ / 40
  5A  Google Docs                  _____ / 18
  5B  Gmail                        _____ / 15
  5C  End-to-End Orchestration     _____ / 7
CODE QUALITY                     _____ / 15
TESTING                          _____ / 15
DOCUMENTATION                    _____ / 5

SUBTOTAL                         _____ / 165
BONUS                            _____ / 10  (optional)
PENALTIES                        -_____

FINAL SCORE                      _____ / 165  (_____ %)
GRADE                            _____

Notes:
_______________________________________________________________
_______________________________________________________________
```
