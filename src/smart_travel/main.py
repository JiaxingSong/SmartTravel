"""Interactive CLI entry point for SmartTravel.

Run with: python -m smart_travel
"""

from __future__ import annotations

import sys

import anyio
from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, TextBlock

from smart_travel.agents import create_agent_options
from smart_travel.config import load_config
from smart_travel.memory.session import Message
from smart_travel.memory.store import MemoryStore, InMemoryMemoryStore


BANNER = """\
+--------------------------------------------------------------+
|              [SmartTravel] Personal AI Travel Agent          |
|                                                              |
|  Search flights, hotels, and events with natural language.   |
|  Type 'quit' or 'exit' to leave. Press Ctrl+C to cancel.    |
+--------------------------------------------------------------+
"""


def _create_memory_store(config) -> MemoryStore:  # noqa: ANN001
    """Create the appropriate memory store based on configuration."""
    return InMemoryMemoryStore()


async def run_chat() -> None:
    """Run the interactive chat loop."""
    print(BANNER)

    config = load_config()
    memory = _create_memory_store(config)
    session = await memory.create_session()

    from smart_travel.tools.preferences import set_memory_store
    set_memory_store(memory)

    preferences = await memory.get_all_preferences()
    preferences_section = preferences.to_prompt_section()
    options = create_agent_options(preferences_section=preferences_section)

    async with ClaudeSDKClient(options=options) as client:
        while True:
            # Surface any triggered price monitor alerts
            from smart_travel.tools.browser import get_pending_alerts
            alerts = get_pending_alerts()
            if alerts:
                print("\n[SmartTravel Monitor Alert]")
                for alert in alerts:
                    print(f"  {alert}")

            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nGoodbye! Happy travels!")
                break

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("\nGoodbye! Happy travels!")
                break

            await memory.save_message(session.id, Message("user", user_input))

            print()
            await client.query(user_input)

            print("SmartTravel: ", end="", flush=True)
            response_parts: list[str] = []
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="", flush=True)
                            response_parts.append(block.text)
            print()

            if response_parts:
                await memory.save_message(
                    session.id, Message("assistant", "".join(response_parts)),
                )

    await memory.close()


def main() -> None:
    """CLI entry point."""
    try:
        anyio.run(run_chat)
    except KeyboardInterrupt:
        print("\n\nGoodbye! Happy travels!")
        sys.exit(0)


if __name__ == "__main__":
    main()
