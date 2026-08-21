# Arizona — confirmed broken (CAPTCHA wall)

Any Arizona company will land in `manual_review_needed`. Confirmed, not a bug to chase.

**Official lookup:** Arizona Corporation Commission (ACC) Business Search —
https://arizonabusinesscenter.azcc.gov/businesssearch. Arizona runs entity status through the ACC,
not the Secretary of State or Dept of Revenue (Revenue has no entity-status tool).

**Failure:** Research-first bootstrap correctly discovered this real `.gov` URL and correctly
filled the "Business Name" field, but submission is blocked by a mandatory image CAPTCHA
("User validation required to continue") before any results show. No API, bulk-download, or
CAPTCHA-free official alternative exists.

**Decision: not building a CAPTCHA solver for this.** Raised explicitly (including a free-trial
solving-service option) and declined — deliberately defeating an interactive human-verification
test is a different category from bot-detection fingerprint evasion (e.g. the NY/Imperva/
ScrapingBee approach used elsewhere), carries real ToS/legal risk against a government system, and
this tracker's hourly automated-refresh model is exactly the sustained-scraping pattern CAPTCHAs on
entity search tools exist to stop. If re-implemented independently outside this codebase, that's a
separate decision/risk to own — not merged into `engine.py`'s recipe system.

**Manual check:** https://arizonabusinesscenter.azcc.gov/businesssearch — solve the CAPTCHA by hand.
