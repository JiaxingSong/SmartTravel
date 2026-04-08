# Runbook: Add Support for a New Airline

## Step 1: Add login/verify functions

In `src/smart_travel/tools/award_search.py`, add:

```python
async def _login_<airline>(page, account: LoyaltyAccount) -> bool:
    # Navigate to login URL
    # Fill username/email field
    # Fill password field
    # Click submit
    # Wait for load
    # Return await _verify_<airline>_login(page)

async def _verify_<airline>_login(page) -> bool:
    # Check URL for account indicators
    # Check for logged-in DOM elements
    # Return True/False
```

## Step 2: Add scrape function

```python
async def search_<airline>_awards(origin, dest, date, cabin) -> list[AwardResult]:
    return await _search_airline_awards(
        airline="<key>", program="<program name>",
        login_fn=_login_<airline>, verify_fn=_verify_<airline>_login,
        scrape_fn=_scrape_<airline>_page,
        origin=origin, dest=dest, date=date, cabin=cabin,
    )

async def _scrape_<airline>_page(page, origin, dest, date, cabin) -> list[AwardResult]:
    # Navigate to award search URL with params
    # Wait for results
    # Check for bot challenge: if _is_bot_challenge(page.url, body): return error result
    # Scrape points prices from DOM or regex fallback
    # Return list[AwardResult]
```

## Step 3: Register in dispatch map

Add to `_AIRLINE_SEARCH_FNS` dict in `award_search.py`:
```python
_AIRLINE_SEARCH_FNS = {
    ...
    "<key>": search_<airline>_awards,
}
```

## Step 4: Add enrollment flow (optional)

In `src/smart_travel/accounts/registration.py`:
1. Add enrollment URL to `_ENROLL_URLS`
2. Add fill function to `_FILL_FNS`
3. Add program name to `_PROGRAM_NAMES` in `store.py`

## Step 5: Add alias to `_AIRLINE_ALIASES` in `store.py`

```python
_AIRLINE_ALIASES = {
    ...
    "<display name>": "<key>",
}
```

## Step 6: Add tests

In `tests/test_award_search_tools.py`:
- Add `_normalize_airline` test for the new airline
- Add mocked scraper test

## Step 7: Update docs

- Add airline to `docs/current-status.md` bot detection table
- Update `docs/architecture.md` if needed
