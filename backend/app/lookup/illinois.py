"""Illinois has no company-name search at all — MyTax Illinois' "Verify a
Registered Business" tool (mytax.illinois.gov/?Link=VerifyBus) only accepts an
ID lookup (Account ID, Federal Employer ID #, etc). We use the company's FEIN
(Company.ein). No bot protection encountered here — confirmed reachable and
correct against a real company (Boeing, EIN 91-0425694) by hand before writing
this adapter.

The page doesn't return a single "status" field like Texas/New York — it lists
which tax registrations the business is "currently active for" (Unemployment
Insurance, IL Withholding Income Tax, IL Business Income Tax, etc), or states
outright "This business is not currently active for any accounts." for a
fully inactive registrant (confirmed against a real inactive business — Wavicle
Data Solutions LLC, EIN 46-1800742). We treat "IL Business Income Tax"
appearing in the active list as the franchise/income tax account status.

If a company has no EIN on file, one is discovered via a real web search
(same mechanism generic.py uses to discover a state's search tool) rather than
failing outright. Because a web-searched EIN can be wrong (aggregator sites,
stale data, same-name-different-company mixups), the result is only trusted
if the page's echoed "Legal Business Name" actually matches the company being
checked — otherwise this raises LookupNotFound rather than silently reporting
some other business's status.
"""
import logging
import re

from playwright.sync_api import sync_playwright

from ..llm_client import call_structured, call_with_web_search
from ..models import StatusEnum
from .base import LookupResult, LookupNotFound, LookupBlocked, settle, page_looks_blocked

log = logging.getLogger("illinois_adapter")

SEARCH_URL = "https://mytax.illinois.gov/?Link=VerifyBus"
ACTIVE_MARKER = "currently active for the following"
NOT_ACTIVE_MARKER = "not currently active for any accounts"
NO_RECORD_MARKER = "No record was found for the ID entered"
INCOME_TAX_LABEL = "Business Income Tax"
SOURCE_SCRIPT = "illinois_adapter"

EIN_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "ein": {"type": ["string", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": ["ein", "reasoning"],
    "additionalProperties": False,
}


def _normalize(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()


def _names_match(company_name: str, legal_name: str) -> bool:
    a, b = _normalize(company_name), _normalize(legal_name)
    return bool(a) and bool(b) and (a in b or b in a)


def _discover_ein(company_name: str) -> str:
    answer = call_with_web_search(
        prompt=(
            f"What is the Federal Employer Identification Number (EIN) for the company "
            f"'{company_name}', a business operating in Illinois? Only answer with an EIN you "
            "found stated in a real source (SEC filings, IRS-recognized listings, business "
            "registries, the company's own disclosures) — if you can't find one with reasonable "
            "confidence, say so plainly rather than guessing."
        ),
        purpose="discover_ein",
        source_script=SOURCE_SCRIPT,
    )
    extraction = call_structured(
        prompt=(
            "Extract the EIN (format ##-#######) from this research answer, only if one is "
            f"actually stated. Respond ein=null if no specific EIN is given.\n\n{answer}"
        ),
        schema=EIN_SEARCH_SCHEMA,
        purpose="extract_ein",
        source_script=SOURCE_SCRIPT,
    )
    return _clean_ein(extraction.get("ein"))


def _clean_ein(ein):
    """Guards against the model echoing the word "null"/"none"/"n/a" as a string
    instead of using the JSON null type — that string is truthy in Python, so left
    unchecked it gets treated as a real EIN, saved to the company record, and then
    silently breaks every check after (digit-strips to an empty ID, which the site
    accepts but returns nothing useful for)."""
    if not ein:
        return None
    stripped = ein.strip()
    if not stripped or stripped.lower() in ("null", "none", "n/a", "na"):
        return None
    return stripped


def _extract_legal_name(body_text: str) -> str:
    match = re.search(r"Legal Business Name:\s*\n?(.+)", body_text)
    return match.group(1).strip() if match else ""


def _select_id_type(page, option_text: str):
    page.get_by_role("button", name="Toggle Combobox").first.click()
    page.wait_for_timeout(500)
    for li in page.query_selector_all("li"):
        if (li.inner_text() or "").strip() == option_text:
            li.click()
            return
    raise LookupBlocked(f"ID Type option '{option_text}' not found in dropdown — page layout may have changed")


def _fill_id_field(page, value: str):
    for selector in ("#Dd-6", "#Dd-7"):
        el = page.query_selector(selector)
        if el and el.is_visible():
            el.fill(value)
            return
    raise LookupBlocked("Could not find a visible ID input field after selecting ID Type")


def _active_registrations(body_text: str) -> list[str]:
    lines = body_text.splitlines()
    for i, line in enumerate(lines):
        if ACTIVE_MARKER in line:
            items = []
            for follow in lines[i + 1:]:
                stripped = follow.strip()
                if not stripped or stripped in ("Back", "Scroll for More"):
                    break
                items.append(stripped)
            return items
    return []


def lookup(company_name: str, entity_number: str = None, ein: str = None) -> LookupResult:
    ein = _clean_ein(ein)
    discovered_ein = None
    if not ein:
        log.info(f"  [illinois] no EIN on file for '{company_name}' — searching the web for one")
        ein = _discover_ein(company_name)
        if not ein:
            raise LookupNotFound(f"No EIN on file for '{company_name}' and web search found none either")
        discovered_ein = ein

    log.info(f"  [illinois] verifying '{company_name}' by FEIN on MyTax Illinois")
    digits = re.sub(r"[^0-9]", "", ein)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(SEARCH_URL, timeout=30000)
            settle(page)
            _select_id_type(page, "Federal Employer ID #")
            _fill_id_field(page, digits)
            page.get_by_role("button", name="Search").first.click()
            settle(page)
            page.wait_for_timeout(4000)

            source_url = page.url
            body_text = page.inner_text("body")

            if page_looks_blocked(body_text):
                raise LookupBlocked(
                    f"Page at {source_url} looks like a bot-detection challenge or block page "
                    f"({len(body_text.strip())} chars of content) — not attempting extraction."
                )

            if NO_RECORD_MARKER in body_text:
                raise LookupNotFound(f"No record found for FEIN '{ein}' on MyTax Illinois")

            legal_name = _extract_legal_name(body_text)
            if legal_name and not _names_match(company_name, legal_name):
                raise LookupNotFound(
                    f"FEIN '{ein}' resolved to a different business ('{legal_name}') than "
                    f"'{company_name}' — refusing to report someone else's status"
                )

            if NOT_ACTIVE_MARKER in body_text:
                status = StatusEnum.forfeited
                confidence = 0.9
            else:
                active = _active_registrations(body_text)
                if any(INCOME_TAX_LABEL in item for item in active):
                    status = StatusEnum.active
                    confidence = 0.9
                elif active:
                    # Found and active for other registrations, but not income tax specifically.
                    status = StatusEnum.forfeited
                    confidence = 0.6
                else:
                    status = StatusEnum.unknown
                    confidence = 0.4

            return LookupResult(
                status=status,
                source_url=source_url,
                raw_extract=body_text[:4000],
                confidence=confidence,
                screenshot_path=None,
                discovered_ein=discovered_ein,
            )
        finally:
            browser.close()
