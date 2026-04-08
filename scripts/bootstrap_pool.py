#!/usr/bin/env python
"""Bootstrap the SmartTravel account pool.

Creates email (Outlook if ANTICAPTCHA_API_KEY set, mail.tm fallback),
registers airline loyalty accounts, and reports pool status.

Usage:
    python scripts/bootstrap_pool.py
"""

from __future__ import annotations

import asyncio
import io
import sys

# Force UTF-8 on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, "src")


async def main() -> None:
    import logging
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    from smart_travel.accounts.email_manager import get_email_manager
    from smart_travel.accounts.registration import register_account
    from smart_travel.accounts.store import get_account_store

    airlines = ["united", "alaska", "delta", "aa"]
    store = get_account_store()

    # Step 1: Email
    print("=" * 60)
    print("STEP 1: Ensure email account exists")
    print("=" * 60)
    mgr = get_email_manager()
    email = await mgr.get_or_create_email()
    if email:
        print(f"  Email: {email.address}")
        print(f"  Provider: {email.domain}")
        print(f"  Verified: {email.verified}")
    else:
        print("  FAILED: Could not create email")
        print("  Set ANTICAPTCHA_API_KEY for Outlook, or POOL_BASE_EMAIL for manual")
        return

    # Step 2: Register airline accounts
    print()
    print("=" * 60)
    print("STEP 2: Register airline loyalty accounts")
    print("=" * 60)
    for airline in airlines:
        status = store.get_pool_status(airline)
        if status["active"] > 0:
            print(f"  {airline}: already has {status['active']} active account(s) -- skipping")
            continue

        print(f"  {airline}: registering...", end=" ", flush=True)
        try:
            acct = await register_account(airline)
            if acct:
                print(f"OK (#{acct.loyalty_number})")
            else:
                print("FAILED")
        except Exception as e:
            print(f"ERROR: {e}")

    # Step 3: Pool status
    print()
    print("=" * 60)
    print("POOL STATUS")
    print("=" * 60)
    for airline in airlines:
        s = store.get_pool_status(airline)
        print(
            f"  {airline:8s}: "
            f"total={s['total']} active={s['active']} "
            f"cooling={s['cooling_down']} locked={s['locked']}"
        )

    total_active = sum(store.get_pool_status(a)["active"] for a in airlines)
    print()
    if total_active > 0:
        print(f"Pool ready: {total_active} active account(s) across {len(airlines)} airlines")
    else:
        print("Pool empty. Check logs above for errors.")


if __name__ == "__main__":
    import anyio
    anyio.run(main)
