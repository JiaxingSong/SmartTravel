# CLAUDE.md

SmartTravel — AI-powered travel agent with browser automation and award/points search.

## Quick Reference

| What | Where |
|------|-------|
| Full architecture + module map | `docs/architecture.md` |
| Current status + blockers | `docs/current-status.md` |
| Design rationale | `docs/design-decisions.md` |
| Bootstrap account pool | `docs/runbooks/bootstrap-pool.md` |
| Add a new airline | `docs/runbooks/add-airline.md` |
| Fix bot detection issues | `docs/runbooks/troubleshoot-bot-detection.md` |

## Build & Run

```bash
pip install -e ".[all]"          # all deps including playwright-stealth
playwright install chromium
cp .env.example .env             # edit: set ANTHROPIC_API_KEY
python -m smart_travel           # interactive CLI
```

## Test

```bash
pytest                                              # 186 unit tests
PYTHONIOENCODING=utf-8 python tests/test_e2e.py     # E2E (requires live agent)
```

## Key Modules

- **Tools**: `src/smart_travel/tools/` — 9 MCP tools (browser, award, account, preferences)
- **Accounts**: `src/smart_travel/accounts/` — pool store, sessions, registration, email
- **Agent**: `src/smart_travel/agents.py` — system prompt + tool registration
- **CLI**: `src/smart_travel/main.py` — chat loop entry point

## Env Vars

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API (via proxy or direct) |
| `BROWSER_HEADLESS` | No | `true` | Headed mode for debugging |
| `BROWSER_TIMEOUT_MS` | No | `30000` | Playwright timeout |
| `ACCOUNT_STORE_KEY` | No | `""` | XOR key for account file obfuscation |
| `ANTICAPTCHA_API_KEY` | No | — | FunCaptcha solver for Outlook registration |
| `POOL_BASE_EMAIL` | No | — | Real email for +tag airline registration |
| `POOL_MIN_ACCOUNTS` | No | `2` | Min accounts per airline in pool |
| `SESSION_MAX_AGE_HOURS` | No | `12` | Browser session reuse window |

## Conventions

- Python 3.10+, 4-space indent, type hints on public functions
- Tests: pytest with `asyncio_mode = "auto"`
- Tools: `@tool` decorator from `claude_agent_sdk`
- Singletons: `get_account_store()`, `get_session_manager()`, `get_email_manager()`
