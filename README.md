# SmartTravel

AI-powered travel search agent built with the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/).

SmartTravel lets you search for flights, hotels, and event tickets through natural language conversations. Ask questions like "Find me flights from Seattle to Tokyo next month under $800" and get formatted, relevant results.

## Features

- **Flight search** — Filter by origin/destination, dates, cabin class, passengers, price range, number of stops
- **Hotel search** — Filter by city, dates, guests, star rating, price range, amenities
- **Event/ticket search** — Filter by city, event type (concert/sports/theater/museum), date range, price range
- **Multi-turn conversations** — Refine searches, compare options, ask follow-up questions
- **Mock data (swappable)** — Ships with realistic mock data; swap in real APIs (Amadeus, SerpAPI, etc.) by changing one import

## Quick Start

```bash
pip install -e .
python -m smart_travel
```

Then type natural language queries:

```
You: Find me flights from Seattle to Tokyo next month under $800
You: What hotels are available in Tokyo with a pool?
You: Any concerts happening in Tokyo this weekend?
```

## Architecture

- `src/smart_travel/data/` — Mock data generators (swap for real API clients)
- `src/smart_travel/tools/` — MCP tool definitions (`@tool` decorated)
- `src/smart_travel/agents.py` — Agent configuration with system prompt
- `src/smart_travel/main.py` — Interactive CLI entry point

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```
