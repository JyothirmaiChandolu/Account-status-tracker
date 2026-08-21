# Alaska — confirmed broken (DataDome hard block)

Any Alaska company will land in `manual_review_needed`. Confirmed, not a bug to chase.

**Official lookup:** Alaska Division of Corporations, Business and Professional Licensing (CBPL),
under Dept of Commerce — https://www.commerce.alaska.gov/cbp/main/search/entities (newer front-end)
/ https://www.commerce.alaska.gov/web/cbpl/Corporations/BusinessSearch.aspx (legacy path, same
backend/domain). No other official alternative exists; everything else (Corporate.AI,
secretaryofstateusa.com, sosbusinesssearch.com, entitysearch.us, secretaryofstate.com) is an
unofficial third-party lookalike — do not use these as a source of truth.

**Retested 2026-08-21** after the `gpt-5-search-api` model fix ([[project-openai-search-model-deprecated]]):

- **Bug 1 resolved** — with the new search model, discovery correctly found the real official URL
  (`commerce.alaska.gov/web/cbpl/Corporations/BusinessSearch.aspx`) instead of the fake private site
  (`alaska.secretaryofstate.directory`) it returned before. That earlier bug looks like it was caused
  by the old deprecated model's poor grounding, not a lasting code defect — though a domain
  verification safeguard (require `.gov`) would still be good defense-in-depth.
- **New finding — DataDome hard block.** The real site returns a 403 with explicit headers:
  `server: DataDome`, `x-datadome-botname: Headless Chrome Client Hint`,
  `x-datadome-isbot: 1`, `x-datadome-ruletype: AI Threats Detection`,
  `x-datadome-traffic-rule-response: hard_block`. This is an unambiguous, explicit automated-traffic
  block by a fourth distinct enterprise bot-management vendor (alongside Imperva/California, Akamai/
  California, Cloudflare-style/Arkansas, Salesforce-Locker/Connecticut).
- **Bug 2 (extraction hallucination on zero matches)** — `backend/app/lookup/generic.py:339-342` —
  still an unfixed latent code risk in general, just didn't reproduce this time since the crawl never
  got past hop 0 to reach an extraction attempt.

**Decision:** not pursuing DataDome bypass — same standing line as
[[project-arizona-captcha-wall]], [[project-arkansas-cloudfront-block]],
[[project-california-bot-walls]], and [[project-connecticut-salesforce-crash]].

**Retested again 2026-08-22 — tried every bypass approach on hand:** plain curl (403, explicit
DataDome hard_block headers), Playwright headless and headed (both 403), real Chrome via
`channel="chrome"` + stealth args (403), `nodriver` (CDP-avoidant browser — reached a DataDome JS
challenge page, not real content). ScrapingBee's paid stealth proxy did get past DataDome once —
reached the real search form (`#EntityName` confirmed) — but submitting a search hit a **second,
separate wall**: the site's own application layer has its own CAPTCHA gate on submission
(`/cbp/main/Captcha` endpoint referenced in the page's JS), independent of DataDome. Same
human-verification-by-design category as Arizona — not attempting to solve it. Two stacked
defenses here, not one; beating DataDome alone wouldn't be enough even if it were reliable (it isn't).

**Manual check:** https://www.commerce.alaska.gov/cbp/main/search/entities — works fine in a normal
human browsing session.
