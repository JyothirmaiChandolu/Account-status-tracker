# State-by-state investigation findings

Running log from the sequential state-by-state review (state #1 onward). Each
file documents why a state's automated lookup does or doesn't work, so it's
not re-investigated from scratch later. Companies in a "confirmed broken"
state are expected to land in `manual_review_needed` — that's correct
behavior, not a bug.

| # | State | Status | Notes |
|---|-------|--------|-------|
| 1 | Alabama | Confirmed broken | Dead server (TCP timeout) — [alabama.md](alabama.md) |
| 2 | Alaska | Confirmed broken + open bugs | Fake site + false-positive extraction — [alaska.md](alaska.md) |
| 3 | Arizona | Confirmed broken | Real site, CAPTCHA-walled — [arizona.md](arizona.md) |
| 4 | Arkansas | Confirmed broken | Real site, UA-fingerprint block fixed, adaptive human-verification wall remains — [arkansas.md](arkansas.md) |
| 5 | California | Confirmed broken | 2 official tools, Imperva-walled and Akamai-walled respectively — [california.md](california.md) |
| 6 | Colorado | Completed (documented elsewhere) | — |
| 7 | Connecticut | Confirmed broken | Real site (Salesforce portal) crashes for any Playwright session; also fixed a deprecated OpenAI search model that had been silently degrading bootstrap for every state — [connecticut.md](connecticut.md) |
| — | New York | Confirmed broken (out of sequence — investigated ad hoc, not part of the alphabetical sweep) | Real site, F5 behavioral bot defense, 5 bypass approaches tried and failed/unreliable; monthly open-data API found as an unwired alternative — [new_york.md](new_york.md) |
| — | New Jersey | Confirmed broken (out of sequence) | No free status check exists at all — real one is a paid, login-gated per-report purchase — [new_jersey.md](new_jersey.md) |
