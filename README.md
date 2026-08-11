# Franchise Tax Account Status Monitoring Dashboard

A dashboard that tracks whether a company's franchise/privilege tax account is
**active** with a given US state, so you don't have to manually check each
state's website. Add a company, the system figures out how to check that
state's official site, and keeps checking on a schedule — emailing you if
anything changes to non-active.

**Live deployment:** frontend + backend on Render, database on Render Postgres,
scheduled checks via GitHub Actions (hourly).

---

## 1. The problem this solves

Every US company owes some form of franchise/privilege tax to its home state
(and any state it operates in). If that tax isn't paid, the state can mark the
company **delinquent**, **forfeited**, or **suspended** — which can quietly
break contracts, financing, and legal standing. Checking this by hand, per
company, per state, is tedious and easy to forget.

There is no single national API for this. Each state publishes its own
status-lookup tool (if it has one at all), with completely different
websites, forms, and status wording.

## 2. How it works (the core idea)

Rather than hand-write a scraper for all 50 states up front, the system uses a
**hybrid, self-healing engine**:

1. **Deterministic adapter** (fastest, free, most reliable) — hand-written
   Playwright automation for a specific state's known-good site. Only Texas
   has one today (`backend/app/lookup/texas.py`), because it's the only state
   proven to have a stable, non-bot-blocked public tool.
2. **Generic LLM-bootstrapped engine** (`backend/app/lookup/generic.py`) —
   for any other state, an LLM is shown the tax authority's homepage and asked
   to navigate to the entity-status search tool, identify the form fields, and
   figure out how to read the result. This "recipe" (search URL, CSS
   selectors, status-label text, value mappings) is **saved to the database**
   (`StateAdapterRecipe` table). Every check after the first replays the saved
   recipe with plain Playwright + regex — **no LLM call**, unless the site
   changes and the recipe breaks.
3. **Manual review fallback** — if neither path works (dead server, bot
   detection, CAPTCHA, no tool exists at all), the company is marked
   `manual_review_needed` with a link to where a human should check by hand.
   The system never guesses or fabricates a status.

This is the single most important architectural decision in the project:
**the LLM cost is paid once per state** (or when a site changes), not once per
check. See `backend/app/engine.py` for the orchestration logic that ties the
three paths together.

### Why most states aren't automated yet

An audit of all 51 states (see "Known limitations" below) found that most
state Department of Revenue websites don't expose a public entity-status
search tool at all — that function usually lives with the **Secretary of
State** instead. Of the states that do have a real tool, several are actively
protected by bot-detection (Cloudflare, Imperva, Akamai, CAPTCHA). This
project does not attempt to evade those protections — it correctly falls back
to `manual_review_needed` instead.

## 3. What happens when you add a company

```
Add Company (name, state)
        │
        ▼
Does this state have a deterministic adapter? ──yes──▶ Run it, get a real answer
        │ no
        ▼
Is there a saved recipe for this state? ──yes──▶ Replay it (no LLM)
        │ no                                          │
        ▼                                        fails? try once more,
Bootstrap a new recipe via LLM                    then mark recipe "broken"
(one-time cost per state)                              │
        │                                              ▼
        ▼                                    manual_review_needed
Save recipe, run it                          (skipped for 24h before
        │                                     retrying — see cooldown below)
        ▼
Real status: active / delinquent / forfeited / suspended / manual_review_needed
        │
        ▼
Save to DB (append-only history) + take a screenshot (evidence)
        │
        ▼
If status is non-active AND different from last time → send email alert
```

**Multi-entity handling:** if a company name matches multiple real filings
(e.g. searching "Chevron Phillips" finds 10 subsidiary entities), each one is
tracked as its own row, grouped together in the dashboard under the searched
name — no data is silently discarded.

**Cooldown:** a state whose pipeline is known to be broken (dead server, bot
wall) is retried once when discovered, then left alone for 24 hours before
trying another full LLM bootstrap. Without this, a broken state would pay for
a fresh bootstrap attempt on every single scheduled run.

## 4. Project structure

```
backend/
  app/
    api.py              FastAPI app — all HTTP endpoints, CORS, startup (seed + migrate)
    engine.py            The core orchestration described above
    models.py             SQLAlchemy models: Company, StatusCheck, TaxAuthority,
                          StateAdapterRecipe, LlmCallLog
    schemas.py           Pydantic request/response models
    database.py          Engine/session setup (SQLite locally, Postgres in prod)
    config.py            Env var loading (.env locally, Render env vars in prod)
    seed.py              Loads state_franchise_tax_authorities.csv into the DB
    migrations.py        Tiny idempotent schema migrations, run on every startup
    logsetup.py          Console logging so you can watch a check happen live
    notifications.py     Email alerts (Gmail SMTP) on status change
    llm_client.py        OpenAI wrapper — every call logged to LlmCallLog for cost tracking
    lookup/
      base.py            Shared types: LookupResult, exceptions, settle(), page_looks_blocked()
      texas.py           Hand-written deterministic adapter (the one proven-working state)
      generic.py         LLM-bootstrapped adapter for every other state
      registry.py        Maps state name → deterministic adapter, if one exists
    run_lookup.py         CLI: test a single company/state check
    run_generic_lookup.py CLI: test the generic engine specifically
    audit_all_states.py   One-time audit script: tests all 51 states with a real company each

frontend/
  src/
    App.jsx                     Top-level layout, state, data loading
    api.js                       Fetch wrapper (backend URL from VITE_API_BASE_URL)
    components/
      Sidebar.jsx                Nav + Reload/Refresh All/Add Company buttons
      StatCards.jsx               Total/Active/Needs Review/States Tracked tiles
      CompanyTable.jsx            Main company list, grouped subsidiaries
      AddCompanyModal.jsx         Add-company form
      CompanyDetailModal.jsx      Bar chart + expandable history for one company
      GroupModal.jsx               Subsidiary group view (all entities under one search)
      BarChart.jsx                 Status-over-time chart (ordinal Y-axis, real dates on X)
    format.js                    IST timestamp formatting

state_franchise_tax_authorities.csv   Reference data: state → tax authority → website
render.yaml                            Render Blueprint (backend, frontend, Postgres)
Dockerfile                              Backend container (Playwright's official image —
                                        needed because Chromium requires system libraries
                                        that Render's native Python buildpack can't install)
.github/workflows/refresh-all.yml       Hourly scheduled trigger for /api/companies/refresh-all
```

## 5. Data model

- **Company** — name, state, optional entity number, optional `parent_group`
  (set when it was discovered as one of several matches under a searched
  name).
- **StatusCheck** — **append-only**. Every check ever run is kept (status,
  confidence, source URL, screenshot path, raw extracted text, timestamp).
  Nothing is ever overwritten or deleted by the system itself — this is the
  audit trail. The dashboard just shows the latest one per company.
- **TaxAuthority** — one row per state, seeded from the CSV: state, authority
  name, website, whether it has a franchise/privilege tax.
- **StateAdapterRecipe** — the "learned" navigation recipe per state (search
  URL, field selectors, status label text, raw-value→status mapping,
  `is_broken` flag, `broken_at` timestamp for the cooldown).
- **LlmCallLog** — every OpenAI call ever made, with token counts and cost, so
  spend is always visible (`SELECT SUM(cost_usd) FROM llm_call_logs`).

## 6. API endpoints (`backend/app/api.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/companies` | List all tracked companies (latest status each) |
| POST | `/api/companies` | Add a company, runs a real check immediately |
| GET | `/api/companies/{id}` | Full detail + status history for one company |
| POST | `/api/companies/{id}/refresh` | Re-check one company now |
| DELETE | `/api/companies/{id}` | Remove a company and its history |
| POST | `/api/companies/refresh-all` | Re-check every tracked company (used by the scheduler) |
| GET | `/api/groups/{name}` | All entities under a subsidiary group |
| DELETE | `/api/groups/{name}` | Remove an entire subsidiary group |
| GET | `/api/manual-review` | Companies currently flagged for manual review |
| GET | `/api/stats` | Dashboard stat-tile numbers |
| GET | `/api/states` | The 51-state reference list (for the Add Company dropdown) |

## 7. Frontend design decisions worth knowing

- **No confidence score shown.** Early versions showed a numeric confidence,
  but it was more confusing than useful. Now: a status either came through
  clearly (shows its badge) or it didn't (shows a plain `—`, no alarm, not
  counted in "Needs Review"). Only genuine `manual_review_needed` (no
  automated path exists) is treated as something to act on.
- **All timestamps shown in IST**, converted explicitly on the frontend
  regardless of server or browser timezone (`frontend/src/format.js`).
- **One-screen layout, no page scroll** — only the company table itself
  scrolls internally if the list grows long.
- **Status colors follow a fixed palette** (not themed) — same colors in the
  table badges, the detail chart, and the email alerts, always meaning the
  same thing: green=active, orange=delinquent, red=forfeited/suspended,
  amber=manual review, gray=unclear.

## 8. Running it locally

**Backend:**
```bash
cd "Tax account status tracker"
.venv/bin/uvicorn backend.app.api:app --port 8001 --reload
```

**Frontend:**
```bash
cd frontend
npm run dev
```

**One-off CLI checks** (useful for debugging a specific state without the UI):
```bash
.venv/bin/python -m backend.app.run_lookup "Company Name" "State"
.venv/bin/python -m backend.app.run_generic_lookup "Company Name" "State"
```

Required `.env` values — see `.env.example`:
```
OPENAI_API_KEY=          # required, LLM bootstrap for new states
DATABASE_URL=            # leave blank for local SQLite
GMAIL_USER=              # for email alerts
GMAIL_APP_PASSWORD=      # Gmail App Password, not your real password
ALERT_TO_EMAIL=          # who receives status-change alerts
FRONTEND_ORIGIN=         # deployed frontend URL, for CORS (prod only)
```

## 9. Deployment (Render)

Defined entirely in `render.yaml` (a Render "Blueprint" — connect the repo,
Render reads this file and creates everything):

- **Backend** — Docker web service (uses `Dockerfile`, based on Microsoft's
  official Playwright image, since it bundles the system libraries Chromium
  needs — Render's native Python buildpack can't install them without root).
- **Frontend** — static site, built with Vite.
- **Database** — Render's managed Postgres (free tier).

On every startup, the backend automatically (`backend/app/api.py`):
1. Creates any missing tables.
2. Runs small idempotent migrations (`migrations.py`) for schema changes made
   after the database was first created.
3. Seeds/updates the `TaxAuthority` table from the CSV.

This means a fresh deploy needs zero manual database setup.

**Scheduling:** Render's free tier doesn't include cron jobs, so
`.github/workflows/refresh-all.yml` (a GitHub Actions scheduled workflow, free)
hits `POST /api/companies/refresh-all` every hour. Requires a `BACKEND_URL`
repo secret pointing at the deployed backend.

**Render free tier caveat:** the web service sleeps after 15 minutes idle.
The hourly job wakes it (slow cold-start, ~30-50s) rather than the dashboard
being instantly live at all times. For an always-instant dashboard, upgrade
the backend to Render's paid Starter tier.

## 10. Cost control

- Every OpenAI call is logged to `llm_call_logs` with token counts and cost.
- A state's recipe is bootstrapped once, then replayed for free on every
  subsequent check — LLM cost scales with *number of states encountered*, not
  number of checks.
- The 24-hour cooldown (`engine.py`) prevents a permanently-broken state from
  re-attempting an expensive bootstrap on every hourly run.

## 11. Known limitations (honest status, as of this writing)

- **Only Texas has a fully proven, reliable, zero-ongoing-LLM-cost pipeline.**
- A batch of 5 more states was individually researched (Alaska, Arizona,
  Arkansas, Colorado, Connecticut) — all had the *correct* URL for their real
  entity-search tool, but every one is blocked by active bot detection
  (CAPTCHA, Cloudflare, Imperva, or a broken Salesforce widget). This project
  does not attempt to bypass those protections.
- The remaining ~45 states have only been through the generic automated audit,
  not individually verified — most currently land on `manual_review_needed`.
- **Delaware** has a real, working search tool (confirmed — found 16 real
  subsidiary filings for a test company), but its results use old-style
  `javascript:__doPostBack(...)` links instead of real URLs, which the
  multi-entity handling doesn't yet support. Documented, not yet fixed.
- Realistic path to broader coverage: either continue the state-by-state
  manual research (confirming each state's actual authority and whether it's
  reachable), or integrate an official state API where one exists (e.g.
  California's SOS publishes a real documented API at `calico.sos.ca.gov`),
  or use a paid compliance-data provider (Middesk, CSC, CT Corporation) for
  states that can't be automated directly.

## 12. Ideas for what's next

- Continue the state-by-state research in batches to grow real coverage
  beyond Texas.
- Fix the Delaware postback-link handling for multi-entity states.
- Wire up an official state API (California's, or others as found) as a
  fourth lookup tier, above the generic LLM engine.
- Move screenshot storage off local disk (ephemeral on Render) to something
  persistent (S3-style) if screenshot history matters long-term.
- Add a periodic "does this recipe still work" spot-check, so a site change
  (like the Texas Comptroller's, mid-project) is caught proactively instead of
  only discovered when a check silently starts returning `unknown`.
