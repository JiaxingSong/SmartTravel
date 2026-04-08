# Design Decisions

## Why browser-only (no APIs)?

Travel APIs (Amadeus, Ticketmaster) require paid keys, have rate limits, and often lack
award/points pricing. Browser automation lets us search any public website — the same sites
a human would use. V3 had Amadeus/Ticketmaster integrations; they were removed in V4 because
browser automation is more flexible and unified.

## Why a self-managed account pool?

Award pricing requires logging into airline loyalty sites. A single account gets rate-limited
or locked. A pool of accounts with LRU rotation and exponential cooldown distributes load and
self-heals after failures. Users never see pool internals.

## Why exponential cooldown instead of immediate lock?

V3 locked accounts after 3 failures permanently. This wastes accounts. V4 uses exponential
backoff (1h → 4h → 24h → permanent) so accounts recover automatically. This mirrors how
real users get temporarily locked out and then can retry.

## Why LRU rotation instead of random?

LRU (least-recently-used) ensures even distribution. Random selection could repeatedly hit
the same account while others sit idle. LRU guarantees every account gets equal use, which
reduces per-account request frequency and lowers bot detection risk.

## Why stealth injection?

Airline sites detect headless browsers via `navigator.webdriver`, empty plugin lists, and
missing `window.chrome`. Stealth injection masks these signals. playwright-stealth is the
preferred solution; a minimal init script is the fallback.

## Why Playwright over Selenium/Puppeteer?

- Async-native (matches anyio/asyncio architecture)
- Built-in `storage_state` for session persistence
- `page.locator()` pierces Shadow DOM by default (critical for Alaska's Auro components)
- `force=True` option for filling hidden inputs
- Good Python ecosystem support

## Why mail.tm for email?

Free REST API, no CAPTCHA, instant account creation. The limitation is airlines reject
the domains. This is a known gap — Outlook registration with CAPTCHA solving is the planned
replacement.

## Why not expose pool management to users?

The OpenAI harness engineering philosophy: "humans steer, agents execute." Users should ask
"what's the point price?" and get an answer. They shouldn't need to know about account pools,
rotation, cooldowns, or registration. The agent handles infrastructure silently.
