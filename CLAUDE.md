# CLAUDE.md

## Project Overview

SmartTravel is a Python CLI application built with the Claude Agent SDK (`claude-agent-sdk`).
It is a locally-deployed personal travel agent that uses Playwright browser automation to search
travel websites on behalf of the user — no fixed APIs, no data aggregation.

**Key capability**: Award/points price search. The agent logs into airline loyalty program
websites (United MileagePlus, Alaska Mileage Plan, Delta SkyMiles, American AAdvantage) using
a self-managed account pool, and scrapes award availability. Account rotation, cooldowns, and
registration are handled transparently — users just ask for prices.

## Build & Run

```bash
pip install -e ".[all]"
playwright install chromium
cp .env.example .env
# Edit .env — see env vars below
python -m smart_travel
```

## Test

```bash
pip install -e ".[dev]"
pytest                                    # 186 unit tests
pytest tests/test_e2e.py -v -s            # E2E scenarios (requires live agent)
PYTHONIOENCODING=utf-8 python tests/test_e2e.py   # Direct E2E runner
```

## Architecture

### Browser tools (`src/smart_travel/tools/browser.py`)
Four `@tool`-decorated functions:
- `web_search` — search Bing via Playwright, return titles/URLs/snippets
- `open_page` — open any URL, return cleaned text
- `fill_form` — open page, fill fields by label/name/placeholder, optionally submit
- `monitor_price` — background price watcher with alert system
Plus `get_pending_alerts()` for the chat loop.

### Award search tools (`src/smart_travel/tools/award_search.py`)
- `search_awards` — top-level MCP tool. Two-step flow:
  1. Discover airlines on a route via `web_search`
  2. For each airline with a pool account, log in and scrape award prices
- Per-airline scrapers: `search_united_awards`, `search_alaska_awards`,
  `search_delta_awards`, `search_aa_awards`
- Shared `_search_airline_awards` helper: pool-aware (LRU rotation, retry on failure,
  cooldown on error, session invalidation on bot challenge)
- `AwardResult` dataclass: airline, program, points, taxes, cabin, availability
- Helpers: `_parse_points`, `_parse_taxes`, `_normalize_airline`, `_find_airlines_for_route`

### Account pool (`src/smart_travel/accounts/store.py`)
- `LoyaltyAccount` dataclass: airline, email, password, loyalty_number, status
  (active/cooling_down/locked), last_used, cooldown_until, success_count, failed_attempts
- `AccountStore`: JSON file persistence with XOR obfuscation (ACCOUNT_STORE_KEY env var)
  - `get_next_account(airline)` — LRU rotation, auto-recovers expired cooldowns
  - `mark_used(id)` — update last_used + success_count
  - `mark_cooldown(id)` — exponential backoff: 1h → 4h → 24h → permanent lock
  - `get_pool_status(airline)` — active/cooling/locked counts
  - `add_account`, `remove_account`, `list_all`

### Session manager (`src/smart_travel/accounts/sessions.py`)
- `SessionManager`: persistent Playwright browser contexts per account
  - `storage_state` saved as JSON per account_id, reused if < SESSION_MAX_AGE_HOURS old
  - `playwright-stealth` injection (or minimal fallback)
  - `get_authenticated_page(account, login_fn, verify_fn)` → (browser, context, page) | None
  - Human-like helpers: `_human_delay`, `_type_humanlike`

### Auto-registration (`src/smart_travel/accounts/registration.py`)
- `register_account(airline)` — autonomously creates airline loyalty account
- `ensure_pool_minimum(airline)` — tops up pool to POOL_MIN_ACCOUNTS
- Per-airline enrollment flows for United, Alaska (Atmos Rewards), Delta, AA
- Uses `EmailManager` for email address (mail.tm API or POOL_BASE_EMAIL env var)
- **Status**: Alaska enrollment form fields identified (Auro shadow DOM, `force=True`
  fill required). Airline sites reject temp-mail domains — needs real email provider.

### Email manager (`src/smart_travel/accounts/email_manager.py`)
- `EmailManager`: creates/manages disposable email via mail.tm REST API
- `ManagedEmail` dataclass: address, password, JWT token, verified flag
- Inbox reading: `read_inbox(sender_filter, subject_filter)`, `read_message(id)`
- Verification helpers: `extract_verification_link`, `extract_verification_code`
- **Limitation**: Airlines reject mail.tm domains (e.g. `deltajohnsons.com`).
  Real email provider needed — GMX.com nearly worked (CAPTCHA solver needed).

### Account management tools (`src/smart_travel/tools/account_tools.py`)
- `add_award_account` — save loyalty credentials (password never echoed back)
- `list_award_accounts` — show masked emails, status, no passwords

### Preference tools (`src/smart_travel/tools/preferences.py`)
- `save_preference`, `get_preferences` for cross-session personalization

### Agent (`src/smart_travel/agents.py`)
- `create_agent_options(preferences_section, permission_mode)` — configures
  ClaudeAgentOptions with system prompt + 9 MCP tools
- System prompt instructs: use search_awards for points queries, pool is transparent,
  never ask users for account credentials

### CLI (`src/smart_travel/main.py`)
- Interactive chat loop using `ClaudeSDKClient`
- Surfaces monitor alerts on each turn

### E2E test harness (`tests/test_e2e.py`)
- Non-interactive test runner: sends prompts to live agent, asserts on responses
- 6 scenarios: flight search, hotel search, preference save, price monitor,
  multi-city comparison, award search
- Run with: `PYTHONIOENCODING=utf-8 python tests/test_e2e.py`

### Memory (`src/smart_travel/memory/`)
- Session and preference persistence (in-memory via InMemoryMemoryStore)

### Cache (`src/smart_travel/cache/`)
- TTL in-memory cache with max entries and domain-based invalidation

### Config (`src/smart_travel/config.py`)
Reads from environment:
- `BROWSER_HEADLESS` (bool, default true)
- `BROWSER_TIMEOUT_MS` (int, default 30000)
- `MONITOR_CHECK_INTERVAL` (int minutes, default 5)
- `CACHE_TTL` (int seconds, default 300)
- `CACHE_MAX_ENTRIES` (int, default 500)
- `ACCOUNT_STORE_PATH` (str, default .smart_travel_accounts.json)
- `ACCOUNT_STORE_KEY` (str, empty = plaintext)
- `SESSION_DIR` (str, default .smart_travel_sessions)
- `SESSION_MAX_AGE_HOURS` (int, default 12)
- `POOL_BASE_EMAIL` (str, optional — real email for +tag airline registration)
- `POOL_MIN_ACCOUNTS` (int, default 2)

## Current Status & Known Issues

1. **Award search works end-to-end** when accounts are in the pool — LRU rotation,
   stealth sessions, bot challenge detection, exponential cooldown all functional.
2. **Account pool is empty** — auto-registration blocked because airline sites reject
   temp-mail domains. Needs either: (a) real email with +tag support (POOL_BASE_EMAIL),
   (b) GMX CAPTCHA solver (CaptchaFox slider puzzle — got it once at 55% drag), or
   (c) manual account seeding.
3. **E2E test harness validated**: flight search (Kayak works), hotel search (Booking.com
   works), price monitor, preferences all pass live. Award search returns "no accounts"
   correctly when pool is empty.
4. **Bot detection**: United.com returns ERR_HTTP2_PROTOCOL_ERROR. Kayak and Booking.com
   work. Alaska Atmos Rewards enrollment form accessible (shadow DOM, `force=True` fill).

## Conventions

- Python 3.10+
- 4-space indentation
- Type hints on all public functions
- Tests in `tests/` using pytest with `asyncio_mode = "auto"`
- Tools use `@tool` decorator from `claude_agent_sdk`
- Account store uses module-level singleton via `get_account_store()`
- Session manager uses module-level singleton via `get_session_manager()`
