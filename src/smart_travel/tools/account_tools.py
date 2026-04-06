"""MCP tools for managing airline loyalty accounts in SmartTravel."""

from __future__ import annotations

from claude_agent_sdk import tool

from smart_travel.accounts.store import get_account_store


@tool(
    "add_award_account",
    "Add an airline loyalty account so SmartTravel can search award availability "
    "on that airline's website. Supported airlines: united, alaska, delta, aa. "
    "Credentials are stored locally in an obfuscated JSON file. "
    "Call this when the user provides their loyalty account credentials.",
    {
        "airline": str,        # "united", "alaska", "delta", "aa"
        "email": str,          # login email
        "password": str,       # login password
        "loyalty_number": str, # MileagePlus#, Mileage Plan#, SkyMiles#, AAdvantage#
    },
)
async def add_award_account_tool(args: dict) -> dict:
    """Save a loyalty account; confirm without echoing the password."""
    airline = args.get("airline", "").strip()
    email = args.get("email", "").strip()
    password = args.get("password", "").strip()
    loyalty_number = args.get("loyalty_number", "").strip()

    if not airline:
        return {"content": [{"type": "text", "text": "Error: 'airline' is required."}]}
    if not email:
        return {"content": [{"type": "text", "text": "Error: 'email' is required."}]}
    if not password:
        return {"content": [{"type": "text", "text": "Error: 'password' is required."}]}

    store = get_account_store()
    acct = store.add_account(
        airline=airline,
        email=email,
        password=password,
        loyalty_number=loyalty_number,
    )
    masked_email = acct.email[:3] + "***" + acct.email[acct.email.find("@"):]
    return {
        "content": [{
            "type": "text",
            "text": (
                f"Added {acct.program_name} account: {masked_email} "
                f"(loyalty number: {acct.loyalty_number or 'not provided'}). "
                f"You can now use search_awards for {acct.airline} flights."
            ),
        }]
    }


@tool(
    "list_award_accounts",
    "List all configured airline loyalty accounts. Passwords are never shown. "
    "Use this to check which airlines are ready for award price searches.",
    {},
)
async def list_award_accounts_tool(args: dict) -> dict:
    """Return a safe summary of all configured accounts."""
    store = get_account_store()
    all_accounts = store.list_all()

    if not all_accounts:
        return {
            "content": [{
                "type": "text",
                "text": (
                    "No award accounts configured yet.\n"
                    "Add one with: add_award_account(airline='united', email='...', "
                    "password='...', loyalty_number='...')"
                ),
            }]
        }

    lines = ["Configured award accounts:\n"]
    for airline in sorted(all_accounts):
        for acct in all_accounts[airline]:
            status = "LOCKED" if acct["locked"] else "active"
            failures = f", {acct['failed_attempts']} failed login(s)" if acct["failed_attempts"] else ""
            lines.append(
                f"  {airline.title()}: {acct['email']} "
                f"#{acct['loyalty_number']} [{status}{failures}]"
            )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
