# Runbook: Troubleshoot Bot Detection

## Common Symptoms

| Symptom | Likely Cause |
|---------|-------------|
| `ERR_HTTP2_PROTOCOL_ERROR` | Site blocked headless Chromium at network level |
| Page loads but shows "Access Denied" | WAF (Cloudflare, Imperva, DataDome) |
| `_is_bot_challenge` returns True | CAPTCHA or verification page shown |
| Login succeeds but award search returns empty | Session not properly authenticated |
| `TargetClosedError` | Page navigated away or browser crashed |

## Fixes

### ERR_HTTP2_PROTOCOL_ERROR (United, sometimes Delta)

United.com aggressively blocks all automated browsers. No reliable fix.
- Try headed mode: `BROWSER_HEADLESS=false`
- Try different times of day (less aggressive during off-peak)
- Consider using a residential proxy

### Bot challenge detected

```python
# The _is_bot_challenge() function checks for:
# - URL containing /blocked, /challenge, /captcha
# - Body text containing "access denied", "verify you are human", etc.
```

Fixes:
1. **Invalidate session**: delete `.smart_travel_sessions/<account_id>.json`
2. **Use headed mode**: `BROWSER_HEADLESS=false` — some challenges auto-pass
3. **Install playwright-stealth**: `pip install playwright-stealth`
4. **Add browser args**: already using `--disable-blink-features=AutomationControlled`

### Login works but session expires quickly

The session manager saves `storage_state` and reuses it for up to `SESSION_MAX_AGE_HOURS`
(default 12). If sessions expire sooner:
- Reduce `SESSION_MAX_AGE_HOURS` to 1-2
- Force fresh login: delete the session file

### Shadow DOM inputs not filling (Alaska/Auro components)

Alaska uses Auro Design System with Shadow DOM. Standard `page.fill()` fails because
inputs have `util_displayHiddenVisually` class.

Fix: use `force=True`:
```python
await page.locator('input[name="firstName"]').first.fill(value, force=True)
```

Or use `page.locator()` which pierces Shadow DOM by default (unlike `page.query_selector`).

### All accounts locked

Check pool status:
```python
from smart_travel.accounts.store import get_account_store
store = get_account_store()
print(store.get_pool_status("united"))
```

Reset a specific account:
```python
store.reset_failures("account-uuid")
```

Or wait — cooling_down accounts auto-recover when `cooldown_until` expires.
