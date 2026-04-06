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
- **Multi-site comparison** — SmartTravel searches multiple sites and summarises the best options.
- **Proactive price monitoring** — say "watch this flight and alert me if it drops below $400"
  and SmartTravel checks in the background and alerts you on your next message.
- **Remembers your preferences** — home city, preferred airlines, cabin class, budget range, and
  more persist across sessions.
- **Runs entirely on your machine** — no servers, no databases, no data aggregation.

## Quick Start

```bash
pip install -e ".[live]"
playwright install chromium
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
python -m smart_travel
```

## Usage

```
You: Find me flights from Seattle to Tokyo next month under $800
You: What hotels in Tokyo are near Shinjuku with a pool?
You: Watch this flight and alert me if the price drops below $650
```

## Requirements

- Python 3.10+
- Anthropic API key (`ANTHROPIC_API_KEY`)
- Playwright (installed above)

## Architecture

See [CLAUDE.md](./CLAUDE.md) for developer documentation.

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```
