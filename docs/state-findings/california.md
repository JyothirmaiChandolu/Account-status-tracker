# California — confirmed broken (two separate bot-management walls)

Any California company will land in `manual_review_needed`. Confirmed, not a bug to chase.

Two distinct official tools exist, both automation-walled by different bot-management vendors:

**1. SOS Bizfile Online** — https://bizfileonline.sos.ca.gov/search/business — the primary CA
Secretary of State entity search. Protected by **Imperva**: a direct automated request gets a hard
403 ("Access denied — Error 16", `x-iinfo` header confirms Imperva), even from a plain IP with no
proxy involved. Also independently confirmed: proxy/scraping-service IPs (e.g. ScrapingBee's pool)
get blocked even harder via Imperva's IP-reputation feed — shared datacenter IP pools are
pre-blacklisted against serious WAFs before behavior is even evaluated.

**2. FTB Self Serve Entity Status Letter** — https://webapp.ftb.ca.gov/eletter — a separate,
genuinely free, official, login-free tool (Franchise Tax Board, covers Corporations and LLCs, not
partnerships). Loads clean initially, but the search itself is protected by **Akamai Bot Manager**:
submitting a search hangs forever on a "Processing your request..." spinner for any Playwright-driven
request. Confirmed this isn't a simple headless-flag issue — tried both `headless=True` and
`headless=False` with a normal desktop user-agent, both hang identically. Akamai is very likely
detecting the Chrome DevTools Protocol connection itself (which Playwright always uses to drive the
browser), a much deeper signal than headless mode — defeating it would mean not using CDP-based
automation at all, real arms-race effort against a dedicated bot-management product.

**Decision:** not pursuing either bypass — consistent with the standing decision on Arizona's CAPTCHA
and Arkansas's Human Verification wall (declined bot-detection evasion, including proxy/solving
services). Two independent official tools, two independent enterprise bot-management vendors, both
hold.

**Manual check:** either https://bizfileonline.sos.ca.gov/search/business or
https://webapp.ftb.ca.gov/eletter — both work fine in a normal human browsing session.
