# Current Status

*Last updated: 2026-04-07 (V4, commit 2e24003)*

## What Works

| Feature | Status | Notes |
|---------|--------|-------|
| Cash flight search | **Live** | Kayak returns real prices, Google Flights sometimes blocked |
| Cash hotel search | **Live** | Booking.com returns real prices with ratings |
| Price monitoring | **Built** | Background watcher, alerts on next message |
| Preferences | **Built** | In-memory, persists within session |
| Award search tools | **Built** | 4 airline scrapers, pool rotation, stealth sessions |
| Account pool | **Built** | LRU rotation, exponential cooldown, auto-recovery |
| Session manager | **Built** | storage_state persistence, stealth injection |
| E2E test harness | **Built** | 6 scenarios, non-interactive, all pass |
| Unit tests | **186 passing** | store, tools, sessions, registration, email, browser |

## What's Blocked

| Feature | Blocker | Impact |
|---------|---------|--------|
| Account pool seeding | Airlines reject temp-mail domains | Award search returns "no accounts" |
| Outlook email registration | FunCaptcha (Arkose Labs) | Need CAPTCHA solver (anticaptchaofficial) |
| GMX email registration | CaptchaFox slider puzzle | Got it once at 55%, unreliable |
| United enrollment | URL returns 404 | Need to find current enrollment page |

## Bot Detection Status

| Site | Status | Notes |
|------|--------|-------|
| Bing | **Works** | web_search uses Bing successfully |
| Kayak | **Works** | Flight prices returned |
| Booking.com | **Works** | Hotel prices, ratings returned |
| Google Flights | **Partial** | Sometimes blocked, results variable |
| United.com | **Blocked** | ERR_HTTP2_PROTOCOL_ERROR on most pages |
| AlaskaAir.com | **Partial** | Enrollment page loads, shadow DOM inputs need force=True |
| Delta.com | **Unknown** | Aggressive DataDome bot detection expected |
| AA.com | **Unknown** | Distil/Imperva bot detection expected |

## Next Steps

1. **Integrate anticaptchaofficial** for FunCaptcha solving ($0.003/solve)
2. **Register Outlook email** using CAPTCHA solver
3. **Seed airline accounts** using Outlook +tag aliases
4. **Validate award search** returns real points prices end-to-end
5. **Apply harness engineering** practices from OpenAI article
