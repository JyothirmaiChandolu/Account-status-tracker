# Connecticut — confirmed broken (Salesforce Locker Service crash)

Any Connecticut company will land in `manual_review_needed`. Confirmed, not a bug to chase.

**Official lookup:** Business.CT.gov → Online Business Search —
https://service.ct.gov/business/s/onlinebusinesssearch — a Salesforce Experience Cloud portal run
by the Office of the Secretary of the State. (The generic "Search Office of the Secretary of the
State" box on `portal.ct.gov/sots/business-services/bsd` is a site-wide search, not this tool —
bootstrap initially mistook it for the real one, same false-positive class as Arizona/NJ.)

**Root cause:** Salesforce's Lightning Web Components security sandbox ("Locker Service") throws a
JS error during page init for any Playwright-driven session:
```
Locker evaluation error: Cannot read properties of undefined (reading 'parentNode')
jQuery.Deferred exception: Cannot read properties of undefined (reading '$$lwcNodeObservers$$')
```
No HTTP error at any point (no 403, no CAPTCHA, no known WAF header) — purely a client-side crash.
Confirmed reproducible across every normal-browser-realism fix tried: headless vs headed, real
Chrome channel vs bundled Chromium, realistic viewport, `Referer` header set, simulated mouse
movement/scroll. All five configurations fail identically. That consistency rules out a simple
compatibility fluke — behaves like Salesforce's framework has its own automation-integrity check
(Chrome DevTools Protocol, which Playwright always uses regardless of browser/channel, is a known
detectable signal), same underlying category as Akamai's CDP-based block on California's FTB tool.

**Decision:** not pursuing further (would mean real stealth-patching, not normal debugging) — same
standing line as [[project-arizona-captcha-wall]], [[project-arkansas-cloudfront-block]], and
[[project-california-bot-walls]].

**Manual check:** https://service.ct.gov/business/s/onlinebusinesssearch — works fine in a normal
human browsing session.

**Separately fixed this session (not CT-specific):** the web-search discovery model
(`gpt-4o-mini-search-preview`) was deprecated by OpenAI and had been silently falling back to the
old blind-crawl method. Replaced with `gpt-5-search-api` in `backend/app/llm_client.py`. Checked
logs for every prior state in this sweep (Alabama–California) — all show a successful discovery
call before this deprecation took effect, so none of those findings need retesting.
