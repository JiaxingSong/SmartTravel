"""Interactive setup wizard for SmartTravel API keys.

Run with: ``python -m smart_travel.setup``

Guides the user through configuring API keys for each data source,
validates them with test calls, and writes/merges a ``.env`` file.
"""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m"


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m"


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


# ---------------------------------------------------------------------------
# .env read/write
# ---------------------------------------------------------------------------

def _load_env_file(path: Path) -> dict[str, str]:
    """Parse an existing .env file into a dict."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _write_env_file(path: Path, env: dict[str, str]) -> None:
    """Write a .env file preserving existing comments from .env.example."""
    template = Path(__file__).resolve().parent.parent.parent / ".env.example"
    lines: list[str] = []

    if template.exists():
        for line in template.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                lines.append(line)
            elif "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                val = env.get(key, "")
                lines.append(f"{key}={val}")
        # Add any extra keys not in template
        template_keys = {
            l.split("=", 1)[0].strip()
            for l in template.read_text(encoding="utf-8").splitlines()
            if "=" in l and not l.strip().startswith("#")
        }
        for key, val in env.items():
            if key not in template_keys:
                lines.append(f"{key}={val}")
    else:
        for key, val in sorted(env.items()):
            lines.append(f"{key}={val}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_amadeus(api_key: str, api_secret: str) -> bool:
    """Test Amadeus credentials by requesting an OAuth2 token."""
    try:
        import httpx
    except ImportError:
        print(_dim("  (httpx not installed — skipping validation)"))
        return True

    try:
        resp = httpx.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": api_key,
                "client_secret": api_secret,
            },
            timeout=10,
        )
        if resp.status_code == 200 and "access_token" in resp.json():
            return True
        print(_red(f"  Validation failed: {resp.status_code} {resp.text[:200]}"))
        return False
    except Exception as exc:
        print(_red(f"  Validation error: {exc}"))
        return False


def _validate_ticketmaster(api_key: str) -> bool:
    """Test Ticketmaster key with a simple event search."""
    try:
        import httpx
    except ImportError:
        print(_dim("  (httpx not installed — skipping validation)"))
        return True

    try:
        resp = httpx.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params={"apikey": api_key, "size": 1},
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        print(_red(f"  Validation failed: {resp.status_code} {resp.text[:200]}"))
        return False
    except Exception as exc:
        print(_red(f"  Validation error: {exc}"))
        return False


# ---------------------------------------------------------------------------
# Per-API setup flows
# ---------------------------------------------------------------------------

def _setup_amadeus(env: dict[str, str]) -> None:
    print(f"\n{_bold('━━━ Amadeus (Flights + Hotels — Cash Prices) ━━━')}")
    print("Free test tier: 2,000 calls/month, no credit card required.")
    print("Data: Real-time GDS flight fares and hotel room rates.\n")

    existing_key = env.get("AMADEUS_API_KEY", "")
    existing_secret = env.get("AMADEUS_API_SECRET", "")

    open_url = input("Open Amadeus signup page in browser? [Y/n]: ").strip().lower()
    if open_url != "n":
        webbrowser.open("https://developers.amadeus.com/register")
        print(_dim("  Opened: https://developers.amadeus.com/register"))

    prompt_key = f"API Key [{existing_key[:8]}...]" if existing_key else "API Key"
    prompt_secret = f"API Secret [{existing_secret[:8]}...]" if existing_secret else "API Secret"

    api_key = input(f"  {prompt_key}: ").strip() or existing_key
    api_secret = input(f"  {prompt_secret}: ").strip() or existing_secret

    if api_key and api_secret:
        print("  Validating...", end=" ", flush=True)
        if _validate_amadeus(api_key, api_secret):
            print(_green("✓ Valid"))
            env["AMADEUS_API_KEY"] = api_key
            env["AMADEUS_API_SECRET"] = api_secret
            env.setdefault("AMADEUS_ENVIRONMENT", "test")
        else:
            print(_red("✗ Invalid — not saved"))
    else:
        print(_dim("  Skipped"))


def _setup_ticketmaster(env: dict[str, str]) -> None:
    print(f"\n{_bold('━━━ Ticketmaster (Events — Cash Prices) ━━━')}")
    print("Free tier: 5,000 calls/day, no credit card required.")
    print("Data: Live event listings (concerts, sports, theater).\n")

    existing = env.get("TICKETMASTER_API_KEY", "")

    open_url = input("Open Ticketmaster signup page in browser? [Y/n]: ").strip().lower()
    if open_url != "n":
        webbrowser.open("https://developer.ticketmaster.com/products-and-docs/apis/getting-started/")
        print(_dim("  Opened: Ticketmaster developer portal"))

    prompt = f"API Key [{existing[:8]}...]" if existing else "API Key"
    api_key = input(f"  {prompt}: ").strip() or existing

    if api_key:
        print("  Validating...", end=" ", flush=True)
        if _validate_ticketmaster(api_key):
            print(_green("✓ Valid"))
            env["TICKETMASTER_API_KEY"] = api_key
        else:
            print(_red("✗ Invalid — not saved"))
    else:
        print(_dim("  Skipped"))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _print_summary(env: dict[str, str]) -> None:
    print(f"\n{_bold('━━━ Source Summary ━━━')}\n")

    sources = [
        ("Amadeus (flights + hotels)", bool(env.get("AMADEUS_API_KEY") and env.get("AMADEUS_API_SECRET"))),
        ("Ticketmaster (events)", bool(env.get("TICKETMASTER_API_KEY"))),
        ("Google Flights (browser)", _playwright_available()),
        ("Google Hotels (browser)", _playwright_available()),
        ("Mock data (fallback)", True),
    ]

    for name, active in sources:
        icon = _green("✓") if active else _dim("○")
        print(f"  {icon}  {name}")

    print()


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the interactive setup wizard."""
    print(f"\n{_bold('╔══════════════════════════════════════════════════╗')}")
    print(f"{_bold('║         SmartTravel — API Setup Wizard           ║')}")
    print(f"{_bold('╚══════════════════════════════════════════════════╝')}\n")

    env_path = Path.cwd() / ".env"
    env = _load_env_file(env_path)

    print(f"Config file: {env_path}")
    if env:
        print(f"Found {len(env)} existing key(s)\n")
    else:
        print("No existing .env file found — will create one\n")

    # --- Per-API setup ---
    try:
        _setup_amadeus(env)
        _setup_ticketmaster(env)
    except (EOFError, KeyboardInterrupt):
        print("\n\nSetup cancelled.")
        sys.exit(1)

    # --- Write .env ---
    _write_env_file(env_path, env)
    print(f"\n{_green('✓')} Configuration saved to {env_path}")

    _print_summary(env)
    print("Run `python -m smart_travel` to start the agent.\n")


if __name__ == "__main__":
    main()
