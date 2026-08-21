# New York — confirmed broken (behavioral bot detection, not fixable via tooling)

Any New York company will land in `manual_review_needed`. Confirmed, not a bug to chase
further without a fundamentally different approach (see alternative below).

**Official lookup:** NY Dept of State, Division of Corporations — Corporation and Business
Entity Database at https://apps.dos.ny.gov/publicInquiry/. (NY Tax Dept's tax.ny.gov has no
entity-status tool at all — this is a Secretary-of-State-style legal-standing check, unlike
Texas' franchise tax office.)

**Failure:** apps.dos.ny.gov sits behind F5 Distributed Cloud Bot Defense (`TSPD` challenge
script). Real site, real form confirmed by hand (manual browsing always works; form fields
confirmed: `#searchBy`, `#entityname`, `#nameType`, `#searchFunctionality`, entity-type
checkboxes `#Corporation`/`#LimitedLiabilityCompany`/`#LimitedPartnership`/
`#LimitedLiabilityPartnership`; results render as a real `<table>`). Every automation approach
tried failed or was unreliable:

- Plain Playwright (headless & headed, bundled Chromium): blocked every time (`ERR_CONNECTION_RESET`).
- Real Chrome via `channel="chrome"` + `--disable-blink-features=AutomationControlled` +
  `navigator.webdriver` override: blocked every time.
- `nodriver` (CDP `Runtime.enable`-avoidant browser, built specifically to dodge this class of
  detection): blocked every time.
- ScrapingBee stealth proxy (paid, residential IP rotation, `js_scenario` to drive the form):
  ~1-in-4 success across 5 attempts — not deterministic, not something to depend on for
  scheduled checks.
- Ruled out IP-level lockout specifically: manual browsing from the same machine/network kept
  working throughout every automated attempt above.

Conclusion: looks like behavioral detection (mouse movement/timing), not just a static
fingerprint — property spoofing doesn't fix that, and OS-level human-input simulation isn't
viable for an unattended hourly job anyway.

**Alternative found — not yet wired in.** `data.ny.gov` publishes "Active Corporations:
Beginning 1800" (Socrata dataset `n9v6-gdp6`), a free public API, no bot protection. Confirmed
correct: looked up "Future Roots LLC" → same DOS ID (6653978) as the live UI. Tradeoff: it's a
**monthly snapshot** ("active as of the last business day of the specified month"), not live —
fine for periodic monitoring, not for same-day status changes. `backend/app/lookup/newyork.py`
currently still targets the live UI via Playwright and will keep failing until this is swapped
in for the API.

**Manual check:** https://apps.dos.ny.gov/publicInquiry/ — Search By "Entity Name", Search
Functionality "Begins With", (status filter) "AllStatuses", tick the relevant Entity List
checkbox (Corporation/LLC/LP/LLP).

**Re-verify periodically** — bot-defense vendors and rulesets change; a block today isn't
necessarily permanent.
