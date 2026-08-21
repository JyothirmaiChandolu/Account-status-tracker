# Alaska — confirmed broken, plus two open code bugs

Any Alaska company will land in `manual_review_needed` once the bugs below are fixed. Currently,
without the fix, it can silently return a **false "active" status** instead — worse than
manual review.

**Official lookup:** Alaska Division of Corporations, Business and Professional Licensing (CBPL),
under Dept of Commerce — https://www.commerce.alaska.gov/cbp/main/search/entities. No other
official alternative exists; everything else (Corporate.AI, secretaryofstateusa.com,
sosbusinesssearch.com, entitysearch.us, secretaryofstate.com) is an unofficial third-party
lookalike — do not use these as a source of truth.

**Bug 1 — discovery trusts non-`.gov` domains.** The research-first bootstrap step
(`_discover_starting_url` in `backend/app/lookup/generic.py`) returned
`alaska.secretaryofstate.directory` — a *privately owned* site that says so on its own page —
and the crawler treated it as legitimate because nothing checks the domain is actually official.

**Bug 2 — extraction hallucinates on zero matches.** In `_run_search_and_extract`
(`backend/app/lookup/generic.py:339-342`), when 0 links match and `has_result_list` is false and
the page doesn't say "no results," code assumes "this state's search goes straight to a detail
page" and extracts anyway. On the fake site, the LLM was fed irrelevant page content and
hallucinated `status=active, confidence=0.95` instead of refusing.

**Status:** both bugs reported, fix intentionally deferred (user chose not to fix yet, moved to
next state). Fix direction: verify discovered URL is a real government domain before trusting it;
don't extract from a page unless a match was actually confirmed.

**Manual check:** https://www.commerce.alaska.gov/cbp/main/search/entities (was under maintenance
as of 2026-08-18 — retry later).
