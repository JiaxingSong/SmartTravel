# CLAUDE.md

## Project Overview

SmartTravel is a Python CLI application built with the Claude Agent SDK (`claude-agent-sdk`).
It is a locally-deployed personal travel agent that uses Playwright browser automation to search
travel websites on behalf of the user — no fixed APIs, no data aggregation.

## Build & Run

```bash
pip install -e ".[live]"
playwright install chromium
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
python -m smart_travel
```

## Test

```bash
pip install -e ".[dev]"
pytest
```

## Architecture

- **Browser tools** (`src/smart_travel/tools/browser.py`): Four `@tool`-decorated functions —
  `web_search`, `open_page`, `fill_form`, `monitor_price` — plus `get_pending_alerts()` for the
  chat loop.
- **Preference tools** (`src/smart_travel/tools/preferences.py`): `save_preference` and
  `get_preferences` for cross-session personalization.
- **Agent** (`src/smart_travel/agents.py`): `ClaudeAgentOptions` with a browser-agent system
  prompt and MCP server registration.
- **CLI** (`src/smart_travel/main.py`): Interactive chat loop using `ClaudeSDKClient`. Checks
  for monitor alerts on each turn.
- **Memory** (`src/smart_travel/memory/`): Session and preference persistence (in-memory).
- **Cache** (`src/smart_travel/cache/`): TTL in-memory cache.
- **Config** (`src/smart_travel/config.py`): Reads `BROWSER_HEADLESS`, `BROWSER_TIMEOUT_MS`,
  `MONITOR_CHECK_INTERVAL`, `CACHE_TTL`, `CACHE_MAX_ENTRIES` from environment.

## Conventions

- Python 3.10+
- 4-space indentation
- Type hints on all public functions
- Tests in `tests/` using pytest
