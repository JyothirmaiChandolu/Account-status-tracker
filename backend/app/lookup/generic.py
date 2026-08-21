import json
import logging
import re
import uuid
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from ..llm_client import call_structured, call_with_web_search
from ..models import StatusEnum, StateAdapterRecipe
from .base import (
    LookupResult, LookupNotFound, LookupBlocked, MultipleMatchesFound, settle, page_looks_blocked,
    DESKTOP_USER_AGENT,
)

log = logging.getLogger("generic_engine")

MAX_HOPS = 5
SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "backend" / "data" / "screenshots"

NO_RESULTS_PATTERNS = [
    "showing 0 to 0 of 0 entries",
    "no matching records found",
    "no results found",
    "no records found",
    "0 results",
]

FIND_SEARCH_PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "found_form_page": {"type": "boolean"},
        "chosen_link_href": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["found_form_page", "chosen_link_href", "reason"],
    "additionalProperties": False,
}

IDENTIFY_FORM_SCHEMA = {
    "type": "object",
    "properties": {
        "name_field_selector": {"type": ["string", "null"]},
        "submit_selector": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
    },
    "required": ["name_field_selector", "submit_selector", "confidence"],
    "additionalProperties": False,
}

EXTRACT_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "status_label_used": {"type": "string"},
        "raw_status_value": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["active", "delinquent", "forfeited", "suspended", "unknown"],
        },
        "confidence": {"type": "number"},
    },
    "required": ["status_label_used", "raw_status_value", "status", "confidence"],
    "additionalProperties": False,
}

CLASSIFY_VALUE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["active", "delinquent", "forfeited", "suspended", "unknown"],
        },
    },
    "required": ["status"],
    "additionalProperties": False,
}

EXTRACT_DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "terminology": {"type": "string"},
        "candidate_url": {"type": ["string", "null"]},
        "authority_name": {"type": "string"},
    },
    "required": ["terminology", "candidate_url", "authority_name"],
    "additionalProperties": False,
}


RELEVANT_KEYWORDS = [
    "franchise", "privilege", "tax", "status", "entity", "business", "search",
    "corporation", "llc", "account", "license", "delinquent", "standing",
    "revenue", "register", "filing", "compliance",
]


def _collect_links(page, limit=80):
    all_links = []
    seen = set()
    for a in page.query_selector_all("a"):
        href = a.get_attribute("href") or ""
        text = (a.inner_text() or "").strip()
        if href and text and href not in seen:
            seen.add(href)
            all_links.append({"text": text[:80], "href": href})

    def is_relevant(link):
        low = (link["text"] + " " + link["href"]).lower()
        return any(k in low for k in RELEVANT_KEYWORDS)

    filtered = [l for l in all_links if is_relevant(l)]
    pool = filtered if filtered else all_links
    return pool[:limit]


def _collect_form_elements(page):
    elements = []
    for el in page.query_selector_all("input, button"):
        info = el.evaluate(
            """e => ({
                tag: e.tagName.toLowerCase(),
                id: e.id || null,
                name: e.name || null,
                type: e.type || null,
                text: (e.innerText || e.value || '').trim().slice(0, 40)
            })"""
        )
        elements.append(info)
    return elements


def _find_all_matching_links(page, company_name):
    matches = []
    seen = set()
    needle = company_name.strip().upper()
    for a in page.query_selector_all("a"):
        text = (a.inner_text() or "").strip()
        href = a.get_attribute("href") or ""
        if text and href and needle in text.upper() and href not in seen:
            seen.add(href)
            matches.append({"name": text, "href": href, "element": a})

    if matches:
        return matches

    # Some result tables (e.g. DataTables-style grids) have no real <a href> at
    # all — each row is a plain <td> with a JS click-handler bound to the row.
    # Fall back to matching by cell text and clicking the row itself; href is
    # None since there's no independently-navigable URL for these.
    for cell in page.query_selector_all("td"):
        text = (cell.inner_text() or "").strip()
        if text and needle in text.upper() and text not in seen:
            seen.add(text)
            matches.append({"name": text, "href": None, "element": cell})
    return matches


def _page_shows_no_results(body_text):
    low = body_text.lower()
    return any(p in low for p in NO_RESULTS_PATTERNS)


def _selector_from_info(info):
    if info.get("id"):
        return f"#{info['id']}"
    if info.get("name"):
        return f"[name='{info['name']}']"
    return None


def _discover_starting_url(state: str, source_script: str) -> dict:
    """No predefined path: research what this check is actually called and where
    it actually lives in this state, using real web search — not just crawling
    from whatever URL happens to be in the reference CSV. Every state calls this
    something different and often puts it on an entirely separate domain from
    the tax authority's own homepage (e.g. New Jersey's is on njportal.com, not
    nj.gov). The returned URL is a research lead, not a fact — it still has to
    be live-verified before use."""
    answer = call_with_web_search(
        prompt=(
            f"In the US state of {state}, what is the official government website where the public can look up "
            "a business entity's current legal/tax standing — sometimes called 'franchise tax status', 'certificate "
            "of good standing', 'entity status', 'business entity status report', or similar depending on the state? "
            "Identify: (1) the correct government authority responsible (could be the Department of Revenue, the "
            "Secretary of State, or a separate portal), (2) what this specific check is officially called in this "
            "state, (3) the best URL you can find for it — prefer a general search/lookup tool over a one-off "
            "certificate request if both exist, and prefer a top-level page over a deep link you're not fully sure "
            "of. Note whether it requires payment or an account."
        ),
        purpose="discover_state_authority",
        source_script=source_script,
    )
    return call_structured(
        prompt=(
            "Extract the key facts from this research answer about a US state's business entity status check:\n\n"
            f"{answer}"
        ),
        schema=EXTRACT_DISCOVERY_SCHEMA,
        purpose="extract_discovery",
        source_script=source_script,
    )


def bootstrap_recipe(state: str, authority_homepage: str, source_script: str = "generic_bootstrap") -> StateAdapterRecipe:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=DESKTOP_USER_AGENT)
        try:
            current_url = authority_homepage
            try:
                discovery = _discover_starting_url(state, source_script)
                candidate_url = discovery.get("candidate_url")
                log.info(f"  [bootstrap] research: '{discovery.get('terminology')}' via "
                         f"{discovery.get('authority_name')} — candidate URL: {candidate_url}")
                if candidate_url:
                    page.goto(candidate_url, timeout=15000)
                    settle(page)
                    current_url = candidate_url
                    log.info(f"  [bootstrap] discovered URL loaded successfully, starting there instead of {authority_homepage}")
                else:
                    raise ValueError("no candidate URL returned")
            except Exception as e:
                log.info(f"  [bootstrap] discovered URL unusable ({type(e).__name__}: {e}) — falling back to {authority_homepage}")
                current_url = authority_homepage
                page.goto(current_url, timeout=30000)
                settle(page)

            visited = {current_url}

            found = False
            for hop in range(MAX_HOPS + 1):
                log.info(f"  [bootstrap] hop {hop}: asking LLM to judge {current_url}")
                elements = _collect_form_elements(page)
                links = _collect_links(page)
                has_text_input = any(
                    el.get("tag") == "input" and el.get("type") in (None, "text") for el in elements
                )
                decision = call_structured(
                    prompt=(
                        "You are navigating a US state tax/revenue authority website looking for the dedicated "
                        "BUSINESS ENTITY / FRANCHISE TAX / PRIVILEGE TAX ACCOUNT STATUS SEARCH tool — a page where "
                        "you search a specific company by name and see whether its tax/franchise account status is "
                        "active, delinquent, forfeited, suspended, etc. Do NOT mistake a generic site-wide keyword "
                        "search box (e.g. a top-nav 'search this website' icon) for this tool — that is NOT it. A "
                        "page that only lists LINKS to different search sub-types (e.g. 'Search by Name', 'Search "
                        "by ID') but has no actual text input field of its own is NOT the tool yet — you must "
                        "follow one of those links first to reach the real form.\n\n"
                        f"Current page URL: {current_url}\n"
                        f"Current page form/input elements (JSON): {json.dumps(elements)}\n"
                        f"Links on this page (JSON): {json.dumps(links)}\n\n"
                        "If the current page's form elements above include a real text input for entering a "
                        "business name, respond found_form_page=true. Otherwise pick the single best link to "
                        "follow next toward that tool, respond found_form_page=false with chosen_link_href set. "
                        "If nothing looks promising, respond found_form_page=false and chosen_link_href=null."
                    ),
                    schema=FIND_SEARCH_PAGE_SCHEMA,
                    purpose="find_search_page",
                    source_script=source_script,
                )
                if decision.get("found_form_page") and has_text_input:
                    log.info(f"  [bootstrap] found the search tool at {current_url}")
                    found = True
                    break

                href = decision.get("chosen_link_href")
                if decision.get("found_form_page") and not has_text_input:
                    # LLM wrongly declared victory on a page with no real input (e.g. a
                    # menu of sub-search-type links) — it won't have given us a link to
                    # follow in that case, so fall back to the first relevant link found.
                    href = links[0]["href"] if links else None
                    log.info(f"  [bootstrap] LLM said found_form_page=true but no real text input exists here — "
                             f"overriding, following first relevant link instead: {href}")
                if not href:
                    log.info(f"  [bootstrap] no promising link, giving up: {decision.get('reason')}")
                    break
                next_url = urljoin(current_url, href)
                if next_url in visited:
                    log.info(f"  [bootstrap] link leads somewhere already visited, giving up")
                    break
                visited.add(next_url)
                log.info(f"  [bootstrap] following link to {next_url}")
                page.goto(next_url, timeout=30000)
                settle(page)
                current_url = next_url

            if not found:
                raise LookupNotFound(
                    f"No dedicated entity-status search tool found for state '{state}' within {MAX_HOPS} hops from {authority_homepage}"
                )

            elements = _collect_form_elements(page)

            form_decision = call_structured(
                prompt=(
                    "Here are the input/button elements found on this page (JSON list). Identify which one is "
                    "the TEXT FIELD for entering a business/entity name to search, and which is the SUBMIT button. "
                    "Respond with a selector for each, in this priority order: '#id' if an id is present; else "
                    "\"[name='...']\" if a name is present; else, for the submit button ONLY, if it has neither "
                    "id nor name but has visible text, respond with 'role=button[name=\"EXACT_TEXT\"]' or "
                    "'role=button[name=\"EXACT_TEXT\" i]' (Playwright's ARIA role selector — matches only real "
                    "interactive elements by their exact accessible name, unlike a plain text= selector which can "
                    "wrongly match a heading or paragraph that happens to contain the same word). NEVER use a bare "
                    "'text=...' selector for a button, and NEVER invent jQuery-style pseudo-selectors like "
                    "':contains(...)' — they are not valid CSS and will fail.\n"
                    f"{json.dumps(elements)}"
                ),
                schema=IDENTIFY_FORM_SCHEMA,
                purpose="identify_form_fields",
                source_script=source_script,
            )
            name_selector = form_decision.get("name_field_selector")
            submit_selector = form_decision.get("submit_selector")
            if not name_selector or not submit_selector:
                raise LookupNotFound(f"LLM could not identify search form fields for state '{state}' at {current_url}")
            log.info(f"  [bootstrap] identified fields: name={name_selector}, submit={submit_selector}")

            recipe = StateAdapterRecipe(
                state=state,
                search_page_url=current_url,
                name_field_selector=name_selector,
                submit_selector=submit_selector,
                has_result_list=False,
                status_value_map={},
            )
            return recipe
        finally:
            browser.close()


def _run_search_and_extract(recipe: StateAdapterRecipe, company_name: str, page, source_script: str):
    page.goto(recipe.search_page_url, timeout=30000)
    settle(page)
    page.fill(recipe.name_field_selector, company_name)
    page.click(recipe.submit_selector)
    settle(page)
    page.wait_for_timeout(3000)

    matches = _find_all_matching_links(page, company_name)
    log.info(f"  [search] {len(matches)} matching link(s) found for '{company_name}'")

    if len(matches) == 0:
        if recipe.has_result_list or _page_shows_no_results(page.inner_text("body")):
            raise LookupNotFound(f"No match for '{company_name}' in result list at {page.url}")
        # else: this state's search goes straight to a detail page with no list UI — fall through
    elif len(matches) == 1:
        recipe.has_result_list = True
        matches[0]["element"].click()
        settle(page)
        page.wait_for_timeout(3000)
    else:
        recipe.has_result_list = True
        if any(m["href"] is None for m in matches):
            # No independently-navigable URL per row (JS-click-only result table) —
            # can't split these into separately-checkable entities the way
            # MultipleMatchesFound expects. Documented limitation, same family as
            # Delaware's javascript:__doPostBack() links.
            raise LookupNotFound(
                f"{len(matches)} entities matched '{company_name}' but this site's results have no "
                f"independently-navigable links per row — can't split into separate tracked entities."
            )
        base_url = page.url
        resolved = [{"name": m["name"], "href": urljoin(base_url, m["href"])} for m in matches]
        raise MultipleMatchesFound(resolved)

    return _extract_from_current_page(recipe, page, company_name, source_script)


def _extract_from_current_page(recipe: StateAdapterRecipe, page, entity_label: str, source_script: str):
    source_url = page.url
    body_text = page.inner_text("body")

    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", entity_label.strip())[:40]
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(SCREENSHOT_DIR / f"{recipe.state.lower()}_{safe_name}_{uuid.uuid4().hex[:8]}.png")
    page.screenshot(path=screenshot_path, full_page=True)

    if page_looks_blocked(body_text):
        log.info(f"  [extract] page looks blocked/empty ({len(body_text.strip())} chars) — refusing to guess, raising LookupBlocked")
        raise LookupBlocked(
            f"Page at {source_url} looks like a bot-detection challenge or block page "
            f"({len(body_text.strip())} chars of content) — not attempting extraction."
        )

    status_value_map = recipe.status_value_map or {}

    if recipe.status_label_text:
        pattern = re.escape(recipe.status_label_text.rstrip(":").strip()) + r":?\s*\n\s*([A-Za-z][A-Za-z ]*)"
        m = re.search(pattern, body_text)
        if m:
            raw_value = m.group(1).strip()
            if raw_value in status_value_map:
                status = StatusEnum(status_value_map[raw_value])
                confidence = 0.9
                log.info(f"  [extract] cached label/value hit: '{raw_value}' -> {status.value} (no LLM call)")
            else:
                log.info(f"  [extract] cached label matched but value '{raw_value}' is new — asking LLM to classify it")
                classification = call_structured(
                    prompt=(
                        f"A US state tax authority page shows the label '{recipe.status_label_text}' with value "
                        f"'{raw_value}'. Classify this into one of: active, delinquent, forfeited, suspended, unknown."
                    ),
                    schema=CLASSIFY_VALUE_SCHEMA,
                    purpose="classify_new_status_value",
                    source_script=source_script,
                )
                status = StatusEnum(classification["status"])
                status_value_map[raw_value] = status.value
                recipe.status_value_map = status_value_map
                confidence = 0.75
            return LookupResult(status=status, source_url=source_url, raw_extract=body_text[:4000], confidence=confidence, screenshot_path=screenshot_path), recipe
        log.info("  [extract] cached label didn't match this page — asking LLM for a full extraction")
    else:
        log.info("  [extract] no cached label yet — asking LLM for a full extraction")

    extraction = call_structured(
        prompt=(
            "This is the visible text of a US state tax/revenue authority page after searching for a business "
            f"entity named '{entity_label}'. Find the SPECIFIC field label that sits immediately before the "
            "entity's tax/franchise/privilege tax ACCOUNT STATUS VALUE (e.g. active, delinquent, forfeited, "
            "suspended, in good standing, etc). status_label_used must be the exact narrow field label text "
            "directly attached to that value line (e.g. 'Right to Transact Business in Texas') — NOT a page "
            "title, section heading, or generic header at the top of the page. raw_status_value must be the "
            "exact value text as it literally appears (e.g. 'ACTIVE'). If this page shows NO matching entity at "
            "all (empty search results, zero rows, 'not found'), do not guess — respond status=unknown, "
            "raw_status_value='NO_RESULTS', status_label_used='none'.\n"
            "Page text:\n"
            f"{body_text[:6000]}"
        ),
        schema=EXTRACT_STATUS_SCHEMA,
        purpose="extract_status",
        source_script=source_script,
    )
    status = StatusEnum(extraction["status"])
    status_value_map[extraction["raw_status_value"]] = status.value
    recipe.status_value_map = status_value_map

    # Self-consistency guard: only cache the label if replaying it via regex actually
    # reproduces the value the LLM just reported. Otherwise leave it uncached rather
    # than risk a bad label silently corrupting future replays.
    candidate_label = extraction["status_label_used"].rstrip(":").strip()
    verify_pattern = re.escape(candidate_label) + r":?\s*\n\s*([A-Za-z][A-Za-z ]*)"
    verify_match = re.search(verify_pattern, body_text)
    if verify_match and verify_match.group(1).strip() == extraction["raw_status_value"].strip():
        recipe.status_label_text = candidate_label
    else:
        recipe.status_label_text = None

    return (
        LookupResult(
            status=status,
            source_url=source_url,
            raw_extract=body_text[:4000],
            confidence=extraction["confidence"],
            screenshot_path=screenshot_path,
        ),
        recipe,
    )


def lookup_with_recipe(recipe: StateAdapterRecipe, company_name: str, source_script: str = "generic_replay"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=DESKTOP_USER_AGENT)
        try:
            return _run_search_and_extract(recipe, company_name, page, source_script)
        finally:
            browser.close()


def lookup_detail_url(recipe: StateAdapterRecipe, detail_url: str, entity_name: str, source_script: str = "generic_replay"):
    """Used for a specific sub-entity discovered via a MultipleMatchesFound result —
    goes straight to its known detail page rather than re-running the ambiguous name search."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=DESKTOP_USER_AGENT)
        try:
            page.goto(detail_url, timeout=30000)
            settle(page)
            page.wait_for_timeout(3000)
            return _extract_from_current_page(recipe, page, entity_name, source_script)
        finally:
            browser.close()
