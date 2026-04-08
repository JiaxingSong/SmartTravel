# Runbook: Bootstrap the Account Pool

## Prerequisites

- `pip install -e ".[all]"` and `playwright install chromium`
- `ANTICAPTCHA_API_KEY` set in `.env` (get from https://anti-captcha.com)
- OR: `POOL_BASE_EMAIL` set to a real Gmail/Outlook address

## Automatic Bootstrap

```bash
python scripts/bootstrap_pool.py
```

This will:
1. Create an Outlook email (if ANTICAPTCHA_API_KEY set) or use POOL_BASE_EMAIL
2. Register one account per airline (United, Alaska, Delta, AA)
3. Save all credentials to `.smart_travel_accounts.json`
4. Print pool status summary

## Manual Account Seeding

If automatic registration fails, seed manually:

```python
from smart_travel.accounts.store import AccountStore
store = AccountStore()

store.add_account("united", "your+united@gmail.com", "password", "UA12345678")
store.add_account("alaska", "your+alaska@gmail.com", "password", "1234567890")
store.add_account("delta", "your+delta@gmail.com", "password", "1234567890")
store.add_account("aa", "your+aa@gmail.com", "password", "AA1234567")

# Verify
for airline in ["united", "alaska", "delta", "aa"]:
    print(f"{airline}: {store.get_pool_status(airline)}")
```

## Verify Pool Health

```python
from smart_travel.accounts.store import get_account_store
store = get_account_store()
for airline in ["united", "alaska", "delta", "aa"]:
    s = store.get_pool_status(airline)
    print(f"{airline}: {s['active']} active, {s['cooling_down']} cooling, {s['locked']} locked")
```

## Troubleshooting

- **"No accounts for airline"**: Run bootstrap or manually seed
- **All accounts locked**: Wait for cooldown to expire, or reset:
  ```python
  store.reset_failures("account-uuid-here")
  ```
- **Bot challenge on every login**: Session state may be stale. Delete
  `.smart_travel_sessions/<account_id>.json` to force re-login
