"""Interactive CLI entry point for SmartTravel.

Run with: python -m smart_travel
"""

from __future__ import annotations

import sys

import anyio
from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, TextBlock

from smart_travel.agents import create_agent_options


BANNER = """\
╔══════════════════════════════════════════════════════════════╗
║                    ✈  SmartTravel  ✈                        ║
║         AI-Powered Travel Search Assistant                  ║
║                                                             ║
║  Search flights, hotels, and events with natural language.  ║
║  Type 'quit' or 'exit' to leave. Press Ctrl+C to cancel.   ║
╚══════════════════════════════════════════════════════════════╝
"""


async def run_chat() -> None:
    """Run the interactive chat loop."""
    print(BANNER)

    options = create_agent_options()

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

            # Send query to agent
            print()
            await client.query(user_input)

            # Stream and display the response
            print("\033[1mSmartTravel:\033[0m ", end="", flush=True)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="", flush=True)
            print()  # newline after response


def main() -> None:
    """CLI entry point."""
    try:
        anyio.run(run_chat)
    except KeyboardInterrupt:
        print("\n\nGoodbye! Happy travels! ✈")
        sys.exit(0)


if __name__ == "__main__":
    main()
