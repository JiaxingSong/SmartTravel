"""Interactive CLI entry point for SmartTravel.

Run with: python -m smart_travel
"""

from __future__ import annotations

import sys

import anyio
from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, TextBlock

from smart_travel.agents import create_agent_options, _build_source_status_prompt
from smart_travel.config import load_config, get_source_status
from smart_travel.memory.session import Message
from smart_travel.memory.store import MemoryStore, InMemoryMemoryStore


BANNER = """\
╔══════════════════════════════════════════════════════════════╗
║                    ✈  SmartTravel  ✈                        ║
║         AI-Powered Travel Search Assistant                  ║
║                                                             ║
║  Search flights, hotels, and events with natural language.  ║
║  Type 'quit' or 'exit' to leave. Press Ctrl+C to cancel.   ║
╚══════════════════════════════════════════════════════════════╝
"""


def _create_memory_store(config) -> MemoryStore:  # noqa: ANN001
    """Create the appropriate memory store based on configuration."""
    if config.memory.backend == "postgres":
        from smart_travel.memory.postgres_store import PostgresMemoryStore
        return PostgresMemoryStore()
    return InMemoryMemoryStore()


async def _print_source_diagnostics(source_status) -> None:  # noqa: ANN001
    """Print a startup diagnostics table showing data source availability."""
    print("  Data source status:")
    for entry in source_status.sources:
        if entry.available:
            mark = "\u2713"
        else:
            mark = "\u2717"
        domains = f"[{entry.domain}]"
        if entry.reason == "always_available":
            detail = "always available (demo fallback)"
        elif entry.reason == "configured":
            detail = "configured"
        elif entry.reason == "dependency_missing":
            detail = "not configured (dependency missing)"
        else:
            detail = "not configured (API key missing)"
        print(f"    {mark} {entry.name:<20s} {domains:<12s} \u2014 {detail}")
    if not source_status.any_live_available:
        print("\n  \u26a0  No live data sources configured \u2014 all results will be demo data.")
    print()


async def run_chat() -> None:
    """Run the interactive chat loop."""
    print(BANNER)

    config = load_config()

    # Source diagnostics
    status = await get_source_status()
    await _print_source_diagnostics(status)
    source_status_section = _build_source_status_prompt(status)

    memory = _create_memory_store(config)
    session = await memory.create_session()

    # Inject memory store into preference tools
    from smart_travel.tools.preferences import set_memory_store
    set_memory_store(memory)

    # Load preferences and build agent options
    preferences = await memory.get_all_preferences()
    preferences_section = preferences.to_prompt_section()
    options = create_agent_options(
        preferences_section=preferences_section,
        source_status_section=source_status_section,
    )

    async with ClaudeSDKClient(options=options) as client:
        while True:
            # Read user input
            try:
                user_input = input("\n\033[1mYou:\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nGoodbye! Happy travels! ✈")
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("\nGoodbye! Happy travels! ✈")
                break

            # Save user message
            await memory.save_message(session.id, Message("user", user_input))

            # Send query to agent
            print()
            await client.query(user_input)

            # Stream and display the response
            print("\033[1mSmartTravel:\033[0m ", end="", flush=True)
            response_parts: list[str] = []
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="", flush=True)
                            response_parts.append(block.text)
            print()  # newline after response

            # Save assistant response
            if response_parts:
                await memory.save_message(
                    session.id, Message("assistant", "".join(response_parts)),
                )

    # Cleanup
    await memory.close()
    try:
        from smart_travel.db.pool import close_pool
        await close_pool()
    except Exception:
        pass


def main() -> None:
    """CLI entry point."""
    try:
        anyio.run(run_chat)
    except KeyboardInterrupt:
        print("\n\nGoodbye! Happy travels! ✈")
        sys.exit(0)


if __name__ == "__main__":
    main()
