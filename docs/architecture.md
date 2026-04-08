# Architecture

## System Overview

SmartTravel is a locally-deployed AI travel agent built on `claude-agent-sdk` + Playwright.
The agent searches travel websites via browser automation and returns structured results.

```
User query
    |
    v
ClaudeSDKClient (main.py)
    |
    v
SYSTEM_PROMPT + 9 MCP tools (agents.py)
    |
    +--> Browser tools: web_search, open_page, fill_form, monitor_price
    +--> Award tools:   search_awards
    +--> Account tools: add_award_account, list_award_accounts
    +--> Pref tools:    save_preference, get_preferences
    |
    v
Playwright browser automation (headless Chromium)
    |
    +--> Anonymous: Bing, Kayak, Booking.com, Google Flights
    +--> Authenticated: United, Alaska, Delta, AA (via account pool)
```

## Module Map

### `src/smart_travel/`

| Module | File(s) | Purpose |
|--------|---------|---------|
| CLI entry | `main.py`, `__main__.py` | Interactive chat loop, alert surfacing |
| Agent config | `agents.py` | System prompt, MCP tool registration, `create_agent_options()` |
| Config | `config.py` | `AppConfig` from env vars: browser, cache, account, monitor settings |

### `src/smart_travel/tools/`

| Tool | File | MCP Name | Description |
|------|------|----------|-------------|
| Web search | `browser.py` | `web_search` | Search Bing, return titles/URLs/snippets |
| Open page | `browser.py` | `open_page` | Open URL, return cleaned text |
| Fill form | `browser.py` | `fill_form` | Fill form fields, optionally submit |
| Price monitor | `browser.py` | `monitor_price` | Background price watcher + alerts |
| Award search | `award_search.py` | `search_awards` | Points/miles pricing across airlines |
| Add account | `account_tools.py` | `add_award_account` | Save loyalty credentials |
| List accounts | `account_tools.py` | `list_award_accounts` | Show configured accounts |
| Save pref | `preferences.py` | `save_preference` | Persist user preferences |
| Get prefs | `preferences.py` | `get_preferences` | Retrieve preferences |

### `src/smart_travel/accounts/`

| Module | File | Purpose |
|--------|------|---------|
| Store | `store.py` | `AccountStore`: JSON persistence, XOR obfuscation, LRU rotation, exponential cooldowns |
| Sessions | `sessions.py` | `SessionManager`: Playwright storage_state, stealth injection, human-like delays |
| Registration | `registration.py` | Per-airline enrollment via browser automation |
| Email | `email_manager.py` | Self-managed email (mail.tm API, Outlook planned) |
| CAPTCHA | `captcha_solver.py` | FunCaptcha solver via anticaptchaofficial (planned) |

### `src/smart_travel/memory/`

| Module | File | Purpose |
|--------|------|---------|
| Session | `session.py` | `Message`, `Session` dataclasses |
| Preferences | `preferences.py` | `UserPreferences` with known keys + prompt section |
| Store | `store.py` | `InMemoryMemoryStore` (abstract `MemoryStore` base) |

### `src/smart_travel/cache/`

| Module | File | Purpose |
|--------|------|---------|
| Keys | `keys.py` | `make_cache_key()` — deterministic, order-independent |
| Store | `store.py` | `InMemoryCacheStore` with TTL + max entries + domain eviction |

## Award Search Flow

```
search_awards_tool(origin, dest, date, cabin)
    |
    v
_find_airlines_for_route() -- web_search to discover carriers
    |
    v
For each airline with a supported scraper:
    |
    +--> store.get_next_account(airline)  -- LRU rotation
    |       |
    |       +--> None? --> registration.register_account(airline) --> retry
    |       +--> Account? --> continue
    |
    +--> session_mgr.get_authenticated_page(account, login_fn, verify_fn)
    |       |
    |       +--> Load saved storage_state if < 12h old
    |       +--> Verify session still valid via verify_fn
    |       +--> If expired: fresh login via login_fn
    |       +--> Apply stealth (playwright-stealth or fallback)
    |       +--> On success: save storage_state, reset_failures
    |       +--> On failure: mark_cooldown (1h -> 4h -> 24h -> lock)
    |
    +--> scrape_fn(page, origin, dest, date, cabin)
    |       |
    |       +--> Navigate to award search URL
    |       +--> Check for bot challenge (_is_bot_challenge)
    |       +--> Try DOM selectors for points prices
    |       +--> Fallback: regex on body.innerText
    |
    +--> mark_used(account_id) on success
    |
    v
Combine all results --> format as markdown table --> return
```

## Account Pool Rotation

```
get_next_account("united")
    |
    +--> Auto-recover expired cooldowns (cooldown_until < now)
    +--> Filter to status == "active"
    +--> Sort by last_used ascending (LRU)
    +--> Return oldest (least recently used)
    |
    v
On success: mark_used() --> last_used = now, success_count++
On failure: mark_cooldown() --> exponential backoff:
    Failure #1: 1 hour cooldown
    Failure #2: 4 hour cooldown
    Failure #3: 24 hour cooldown
    Failure #4+: permanent lock
```

## Sensitive Files (gitignored)

- `.smart_travel_accounts.json` — encrypted account credentials
- `.smart_travel_sessions/` — Playwright storage_state per account
- `.smart_travel_email.json` — self-managed email credentials
- `.env` — API keys and config
