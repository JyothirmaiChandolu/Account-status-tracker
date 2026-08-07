"""One-time audit: for every state in the CSV, run a real status check for a
well-known company likely registered there, confirm we get a real result (not
manual_review_needed), and confirm a SECOND check for the same company makes
zero new LLM calls (proving the saved recipe/deterministic adapter is doing
the work, not the LLM, on every check after the first).

Results are written incrementally to audit_results.json so progress can be
inspected while this runs (it's slow — real browser + real government sites).
"""
import json
import time
from pathlib import Path

from .logsetup import configure_logging
configure_logging()

from .database import SessionLocal
from .models import Company, TaxAuthority, LlmCallLog

from .engine import perform_status_check

RESULTS_PATH = Path(__file__).resolve().parents[2] / "audit_results.json"

# One real, well-known company per state, chosen to very likely be registered
# in that state (often headquartered there) to minimize false "not found"
# results caused by bad test data rather than a real pipeline failure.
TEST_COMPANY_BY_STATE = {
    "Alabama": "Regions Financial",
    "Alaska": "Alaska Communications",
    "Arizona": "Avnet",
    "Arkansas": "Walmart",
    "California": "Apple",
    "Colorado": "Chipotle Mexican Grill",
    "Connecticut": "Xerox",
    "Delaware": "Corteva",
    "Florida": "Publix Super Markets",
    "Georgia": "Coca-Cola",
    "Hawaii": "Hawaiian Airlines",
    "Idaho": "Micron Technology",
    "Illinois": "Boeing",
    "Indiana": "Eli Lilly",
    "Iowa": "Principal Financial Group",
    "Kansas": "Spirit AeroSystems",
    "Kentucky": "Humana",
    "Louisiana": "Entergy",
    "Maine": "IDEXX Laboratories",
    "Maryland": "Under Armour",
    "Massachusetts": "Boston Scientific",
    "Michigan": "Ford Motor Company",
    "Minnesota": "Target Corporation",
    "Mississippi": "Cal-Maine Foods",
    "Missouri": "Cerner",
    "Montana": "First Interstate BancSystem",
    "Nebraska": "Union Pacific",
    "Nevada": "MGM Resorts",
    "New Hampshire": "BAE Systems Inc",
    "New Jersey": "Johnson & Johnson",
    "New Mexico": "PNM Resources",
    "New York": "IBM",
    "North Carolina": "Duke Energy",
    "North Dakota": "MDU Resources",
    "Ohio": "Procter & Gamble",
    "Oklahoma": "Devon Energy",
    "Oregon": "Nike",
    "Pennsylvania": "Comcast",
    "Rhode Island": "Hasbro",
    "South Carolina": "Sonoco Products",
    "South Dakota": "Daktronics",
    "Tennessee": "AutoZone",
    "Texas": "MHK Tech Inc",
    "Utah": "Overstock.com",
    "Vermont": "Green Mountain Coffee Roasters",
    "Virginia": "General Dynamics",
    "Washington": "Microsoft",
    "West Virginia": "WesBanco",
    "Wisconsin": "Kohl's",
    "Wyoming": "Sinclair Oil",
    "Washington, D.C.": "National Geographic Society",
}


def audit_state(session, state, company_name):
    entry = {"state": state, "company": company_name}
    t0 = time.time()

    authority = session.query(TaxAuthority).filter_by(state=state).first()
    entry["authority_website"] = authority.website if authority else None

    company = session.query(Company).filter_by(name=company_name, state=state).first()
    if company is None:
        company = Company(name=company_name, state=state)
        session.add(company)
        session.commit()

    llm_before_1 = session.query(LlmCallLog).count()
    try:
        checks1 = perform_status_check(session, company)
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
        entry["result"] = "crashed"
        entry["seconds"] = round(time.time() - t0, 1)
        return entry
    llm_after_1 = session.query(LlmCallLog).count()
    entry["llm_calls_first_run"] = llm_after_1 - llm_before_1

    # Refetch — perform_status_check may have redirected this into a multi-match child
    affected_ids = {c.company_id for c in checks1}
    primary = checks1[0]
    entry["status_first_run"] = primary.status.value
    entry["source_url"] = primary.source_url
    entry["multi_match"] = company.id not in affected_ids
    if entry["multi_match"]:
        entry["match_count"] = len(checks1)

    # Second run: same company (or same anchor) — should need ZERO new LLM calls
    # if the recipe/adapter was properly saved.
    target_company = session.query(Company).filter_by(id=primary.company_id).first()
    llm_before_2 = session.query(LlmCallLog).count()
    try:
        checks2 = perform_status_check(session, target_company)
        entry["status_second_run"] = checks2[0].status.value
    except Exception as e:
        entry["second_run_error"] = f"{type(e).__name__}: {e}"
    llm_after_2 = session.query(LlmCallLog).count()
    entry["llm_calls_second_run"] = llm_after_2 - llm_before_2
    entry["no_llm_on_repeat"] = entry["llm_calls_second_run"] == 0

    entry["result"] = "working" if primary.status.value != "manual_review_needed" else "manual_review_needed"
    entry["seconds"] = round(time.time() - t0, 1)
    return entry


def main():
    session = SessionLocal()
    results = []
    try:
        states = session.query(TaxAuthority).order_by(TaxAuthority.state).all()
        for i, authority in enumerate(states, 1):
            state = authority.state
            company_name = TEST_COMPANY_BY_STATE.get(state)
            if not company_name:
                print(f"[{i}/{len(states)}] SKIP {state} — no test company configured")
                continue
            print(f"[{i}/{len(states)}] === {state}: testing '{company_name}' ===", flush=True)
            entry = audit_state(session, state, company_name)
            results.append(entry)
            print(f"[{i}/{len(states)}] {state} -> {entry.get('result')} "
                  f"(no_llm_on_repeat={entry.get('no_llm_on_repeat')}, {entry.get('seconds')}s)", flush=True)
            RESULTS_PATH.write_text(json.dumps(results, indent=2))
    finally:
        session.close()
    print(f"\nDone. {len(results)} states audited. Results: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
