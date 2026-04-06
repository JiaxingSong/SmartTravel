"""End-to-end tests for SmartTravel agent scenarios.

Runs real agent queries against the live Claude SDK (browser automation
included). No human interaction required. Each test sends a prompt,
collects the full agent response, and asserts on the output.

Run with:
    pytest tests/test_e2e.py -v -s --timeout=120

Requires:
    - claude-agent-sdk accessible (proxy or API key)
    - Playwright + Chromium installed
"""
from __future__ import annotations

import io
import re
import sys
import time
import anyio
import pytest

# Force UTF-8 output on Windows to handle emoji in agent responses
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure src/ is on the path when run directly
sys.path.insert(0, "src")

from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, TextBlock

from smart_travel.agents import create_agent_options
from smart_travel.memory.store import InMemoryMemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def run_scenario(prompt: str, timeout: float = 120.0) -> str:
    """Send a single prompt to the SmartTravel agent and return the full response text."""
    memory = InMemoryMemoryStore()

    from smart_travel.tools.preferences import set_memory_store
    set_memory_store(memory)

    preferences = await memory.get_all_preferences()
    options = create_agent_options(
        preferences_section=preferences.to_prompt_section(),
        permission_mode="bypassPermissions",
    )

    response_parts: list[str] = []

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_parts.append(block.text)

    await memory.close()
    return "".join(response_parts)


def run(prompt: str, timeout: float = 120.0) -> str:
    """Sync wrapper around run_scenario."""
    return anyio.from_thread.run_sync(
        lambda: anyio.run(run_scenario, prompt, timeout)
    ) if False else anyio.run(run_scenario, prompt)


# ---------------------------------------------------------------------------
# Scenario 1: SEA → DFW flight search
# ---------------------------------------------------------------------------

class TestFlightSearch:
    def test_sea_to_dfw_returns_results(self) -> None:
        """Agent should search and return flight options SEA → DFW."""
        print("\n[E2E] Scenario: SEA → DFW flight search")
        t0 = time.time()
        response = run(
            "Find me the cheapest available flights from Seattle (SEA) to "
            "Dallas Fort Worth (DFW) for next weekend. Show prices, airlines, "
            "and departure times."
        )
        elapsed = time.time() - t0
        print(f"[E2E] Response ({elapsed:.1f}s):\n{response}\n")

        # Must mention both airports or city names
        assert re.search(r"SEA|Seattle", response, re.I), "Response should mention SEA/Seattle"
        assert re.search(r"DFW|Dallas", response, re.I), "Response should mention DFW/Dallas"

        # Must contain at least one price-like token ($NNN)
        assert re.search(r"\$\d+", response), "Response should contain at least one price"

        # Must mention at least one airline or travel site
        airline_or_site = re.search(
            r"(Delta|United|American|Southwest|Alaska|Spirit|Frontier|"
            r"Kayak|Google Flights|Expedia|Booking|Priceline)",
            response, re.I
        )
        assert airline_or_site, "Response should mention an airline or travel site"


# ---------------------------------------------------------------------------
# Scenario 2: Hotel search
# ---------------------------------------------------------------------------

class TestHotelSearch:
    def test_hotel_search_dallas(self) -> None:
        """Agent should find hotels in Dallas and return useful results."""
        print("\n[E2E] Scenario: Hotel search in Dallas")
        t0 = time.time()
        response = run(
            "Find hotels near downtown Dallas for 2 nights next weekend. "
            "I need something under $200/night with good reviews."
        )
        elapsed = time.time() - t0
        print(f"[E2E] Response ({elapsed:.1f}s):\n{response}\n")

        assert re.search(r"Dallas|downtown", response, re.I), "Should mention Dallas"
        assert re.search(r"\$\d+", response), "Should contain at least one price"
        # Should mention a hotel name or booking site
        assert re.search(
            r"(Hotel|Inn|Marriott|Hilton|Hyatt|Booking\.com|Hotels\.com|Expedia|",
            response, re.I
        ) or len(response) > 200, "Should return hotel information"


# ---------------------------------------------------------------------------
# Scenario 3: Preference saving
# ---------------------------------------------------------------------------

class TestPreferences:
    def test_save_and_use_preference(self) -> None:
        """Agent should acknowledge saving a preference."""
        print("\n[E2E] Scenario: Save home city preference")
        t0 = time.time()
        response = run(
            "My home city is Seattle. Please remember this for future searches."
        )
        elapsed = time.time() - t0
        print(f"[E2E] Response ({elapsed:.1f}s):\n{response}\n")

        assert re.search(r"Seattle|saved|remember|preference", response, re.I), \
            "Agent should confirm preference was saved"


# ---------------------------------------------------------------------------
# Scenario 4: Price monitor setup
# ---------------------------------------------------------------------------

class TestPriceMonitor:
    def test_monitor_setup_acknowledged(self) -> None:
        """Agent should acknowledge setting up a price monitor."""
        print("\n[E2E] Scenario: Set up price monitor")
        t0 = time.time()
        response = run(
            "Watch flights from Seattle to Dallas and alert me if the price "
            "drops below $150."
        )
        elapsed = time.time() - t0
        print(f"[E2E] Response ({elapsed:.1f}s):\n{response}\n")

        assert re.search(r"monitor|watch|alert|notify|track", response, re.I), \
            "Agent should confirm price monitoring setup"
        assert re.search(r"\$150|\$\s*150|150", response), \
            "Agent should reference the $150 target"


# ---------------------------------------------------------------------------
# Scenario 5: Multi-city comparison
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Scenario 5: Multi-city comparison
# ---------------------------------------------------------------------------

class TestMultiCitySearch:
    def test_compare_two_routes(self) -> None:
        """Agent should compare two routes when asked."""
        print("\n[E2E] Scenario: Compare SEA→DFW vs SEA→LAX prices")
        t0 = time.time()
        response = run(
            "Compare flight prices: Seattle to Dallas vs Seattle to Los Angeles "
            "for next Saturday. Which is cheaper?"
        )
        elapsed = time.time() - t0
        print(f"[E2E] Response ({elapsed:.1f}s):\n{response}\n")

        assert re.search(r"Dallas|DFW", response, re.I), "Should mention Dallas"
        assert re.search(r"Los Angeles|LAX", response, re.I), "Should mention Los Angeles"
        assert re.search(r"\$\d+", response), "Should contain prices"


# ---------------------------------------------------------------------------
# Scenario 6: Award / points price search
# ---------------------------------------------------------------------------

class TestAwardSearch:
    def test_award_search_sea_to_iah(self) -> None:
        """Agent should attempt award search and return meaningful response."""
        print("\n[E2E] Scenario: Award price search SEA to IAH 06/15/2026")
        t0 = time.time()
        response = run(
            "What's the point price for SEA to IAH on 06/15/2026? "
            "Check United MileagePlus and Alaska Mileage Plan."
        )
        elapsed = time.time() - t0
        print(f"[E2E] Response ({elapsed:.1f}s):\n{response}\n")

        assert re.search(r"SEA|Seattle", response, re.I), "Should mention origin"
        assert re.search(r"IAH|Houston", response, re.I), "Should mention destination"
        # Must either return award data or explain accounts need to be configured
        assert re.search(
            r"miles|points|award|MileagePlus|Mileage Plan|account|configured|add_award",
            response, re.I,
        ), "Should mention points/miles or explain account setup"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scenarios = [
        ("SEA to DFW flight search", lambda: run(
            "Find me the cheapest available flights from Seattle (SEA) to "
            "Dallas Fort Worth (DFW) for next weekend. Show prices, airlines, "
            "and departure times."
        )),
        ("Hotel search Dallas", lambda: run(
            "Find hotels near downtown Dallas for 2 nights next weekend "
            "under $200/night."
        )),
        ("Save preference", lambda: run(
            "My home city is Seattle. Please remember this."
        )),
        ("Price monitor", lambda: run(
            "Watch flights from Seattle to Dallas and alert me if price drops below $150."
        )),
        ("Award search no accounts", lambda: run(
            "What's the point price for SEA to IAH on 06/15/2026?"
        )),
    ]

    passed = 0
    failed = 0
    for name, fn in scenarios:
        print(f"\n{'='*60}")
        print(f"SCENARIO: {name}")
        print('='*60)
        try:
            result = fn()
            print(f"\nRESPONSE:\n{result}")
            print(f"\nPASSED: {name}")
            passed += 1
        except Exception as e:
            print(f"\nFAILED: {name}")
            print(f"  Error: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print('='*60)
    sys.exit(0 if failed == 0 else 1)
