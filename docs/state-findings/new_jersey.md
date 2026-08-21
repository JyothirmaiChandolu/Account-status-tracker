# New Jersey — confirmed broken (no free status check exists)

Any New Jersey company will land in `manual_review_needed`. Confirmed, not a bug to chase —
there is no free, public, instant entity-status lookup for New Jersey at all.

**Two different njportal.com tools, easy to confuse:**

1. **Business Name Search** (https://www.njportal.com/DOR/BusinessNameSearch/Search/BusinessName)
   — what the generic bootstrap found and cached (`#BusinessName` / `role=button[name="Search"]`).
   Real site, no bot protection, search works fine. But it is **only a name/entity-ID directory**
   (Business Name, Entity Id, City, Type, Incorporated Date) — confirmed by hand that clicking a
   result row does nothing at all, no detail page, **no status field exists anywhere in this
   tool**. Wrong tool for the job, not a broken one.

2. **Business Entity Status Report** (https://www.njportal.com/dor/businessrecords/entitydocs/businessstatcopies.aspx)
   — the actual official status check. It's a **paid, account-based transaction**: search by
   Business Name/Entity ID/Principal Name/Registered Agent/Associated Name, then add the report
   to a cart and check out — $5.00 + $1.25 online fee per report, "New User"/"Login" required.
   Legacy ASP.NET WebForms wizard (viewstate/postback-heavy, resisted straightforward
   automation even just to get past the search step in testing).

**Why this stays manual_review_needed by design:** the only real status source is a paid,
login-gated per-report purchase. Automating a purchase flow (needs an account + stored payment
method, charges money per check) isn't something to script without explicit sign-off, and
doesn't fit an unattended hourly-check model regardless — cost scales with every check, every
company. This is a business/product decision, not an engineering one.

**Confirmed via real search, for context:** "Johnson & Johnson" matches 55 entities in the name
search (every JNJ subsidiary contains that substring) with no per-row link to disambiguate even
if status were the goal — same no-href-per-row limitation `generic.py` already documents for
Delaware.

**Manual check:** https://www.njportal.com/dor/businessrecords/entitydocs/businessstatcopies.aspx
— requires paying for the report, same as the automated path would.
