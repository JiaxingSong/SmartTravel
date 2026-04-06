# SmartTravel

A locally-deployed personal AI travel agent built with the
[Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/) and
[Playwright](https://playwright.dev/) browser automation.

SmartTravel acts like a knowledgeable friend who opens a browser and searches travel sites on
your behalf — Google Flights, Kayak, Booking.com, airline sites, and more. No travel API keys
required beyond your Anthropic key.

## Features

- **Natural language travel search** — ask anything: "Find flights from Seattle to Tokyo next
  month under $800", "What hotels near the Eiffel Tower have pools?"
- **Award/points price search** — ask "What's the point price for SEA to IAH?" and SmartTravel
  logs into airline loyalty sites (United, Alaska, Delta, AA) to scrape award availability.
- **Self-managed account pool** — airline loyalty accounts are rotated, cooled down, and
  auto-registered transparently. Users never see pool internals.
- **Multi-site comparison** — searches multiple sites and summarises the best options.
- **Proactive price monitoring** — say "watch this flight and alert me if it drops below $400"
  and SmartTravel checks in the background and alerts you on your next message.
- **Remembers your preferences** — home city, preferred airlines, cabin class, budget range, and
  more persist across sessions.
- **Runs entirely on your machine** — no servers, no databases, no data aggregation.

## Quick Start

```bash
pip install -e ".[all]"
playwright install chromium
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and optionally POOL_BASE_EMAIL
python -m smart_travel
```

## Usage

```
You: Find me flights from Seattle to Tokyo next month under $800
You: What hotels in Tokyo are near Shinjuku with a pool?
You: What's the point price for SEA to IAH on June 15?
You: Watch this flight and alert me if the price drops below $650
```

## Requirements

- Python 3.10+
- Anthropic API key (`ANTHROPIC_API_KEY`)
- Playwright + Chromium (installed above)
- Optional: `playwright-stealth` for better anti-detection (`pip install playwright-stealth`)

## Architecture

See [CLAUDE.md](./CLAUDE.md) for full developer documentation including:
- All 9 MCP tools and their signatures
- Account pool rotation and cooldown mechanics
- Session manager with Playwright storage_state persistence
- Auto-registration flow and known limitations
- E2E test harness and validation scenarios

## Running Tests

```bash
pip install -e ".[dev]"
pytest                                    # 186 unit tests
pytest tests/test_e2e.py -v -s            # E2E (requires live agent)
PYTHONIOENCODING=utf-8 python tests/test_e2e.py   # Direct E2E runner
```
