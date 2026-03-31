# CLAUDE.md

## Project Overview

SmartTravel is a Python CLI application built with the Claude Agent SDK (`claude-agent-sdk`).
It provides an interactive travel search agent that can search for flights, hotels, and event tickets
via natural language queries.

## Build & Run

```bash
pip install -e .
python -m smart_travel
```

## Test

```bash
pip install -e ".[dev]"
pytest
```

## Architecture

- **Mock data layer** (`src/smart_travel/data/`): Generates realistic travel data with seeded randomness.
- **MCP tools** (`src/smart_travel/tools/`): Three `@tool`-decorated functions registered via `create_sdk_mcp_server`.
- **Agent** (`src/smart_travel/agents.py`): Configures `ClaudeAgentOptions` with a travel-specialist system prompt.
- **CLI** (`src/smart_travel/main.py`): Interactive chat loop using `ClaudeSDKClient`.

## Conventions

- Python 3.10+
- 4-space indentation
- Type hints on all public functions
- Tests in `tests/` using pytest
