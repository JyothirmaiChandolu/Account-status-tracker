"""Colorado's real entity-status tool lives on a different domain (coloradosos.gov,
Secretary of State) than the original bootstrap's starting point (tax.colorado.gov,
Dept of Revenue) — that's why it landed in manual_review_needed: wrong homepage to
crawl from, not a bot-block or a broken site. The real tool
(coloradosos.gov/biz/BusinessEntityCriteriaExt.do) has no bot protection, real
per-row links, and a "Details" page with a clean Status label:value pair.
Confirmed against a real company (Chipotle Mexican Grill) by hand before writing
this adapter.
"""
import logging
import re
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from ..models import StatusEnum
from .base import LookupResult, LookupNotFound, LookupBlocked, MultipleMatchesFound, settle, page_looks_blocked

log = logging.getLogger("colorado_adapter")

SEARCH_URL = "https://www.coloradosos.gov/biz/BusinessEntityCriteriaExt.do"
# Trade name filings (TradeNameSummary.do) have no Status field at all — a trade name
# isn't a taxable entity in its own right, just a name a real entity operates under.
# Only real entity filings carry the good-standing status we're after.
DETAIL_LINK_SUBSTRING = "BusinessEntityDetail.do"

STATUS_MAP = {
    "GOOD STANDING": StatusEnum.active,
    "DELINQUENT": StatusEnum.delinquent,
}
FORFEITED_KEYWORDS = ("DISSOLV", "REVOK", "WITHDRAW", "EXPIR", "FORFEIT")


def _map_status(raw_value: str) -> StatusEnum:
    upper = raw_value.strip().upper()
    if upper in STATUS_MAP:
        return STATUS_MAP[upper]
    if any(k in upper for k in FORFEITED_KEYWORDS):
        return StatusEnum.forfeited
    return StatusEnum.unknown


def _normalize(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()


def _find_matching_rows(page, company_name: str) -> list[dict]:
    needle = _normalize(company_name)
    matches = []
    for tr in page.query_selector_all("tr"):
        link = None
        for a in tr.query_selector_all("a"):
            href = a.get_attribute("href") or ""
            if DETAIL_LINK_SUBSTRING in href:
                link = a
                break
        if not link:
            continue
        cells = [c.strip() for c in tr.eval_on_selector_all("td", "els => els.map(e => e.innerText)")]
        if len(cells) < 4:
            continue
        name = cells[3]
        if needle not in _normalize(name):
            continue
        matches.append({
            "name": name,
            "href": link.get_attribute("href"),
            "exact": _normalize(name) == needle,
        })
    return matches


def _extract_from_detail(page, entity_label: str) -> LookupResult:
    source_url = page.url
    body_text = page.inner_text("body")

    if page_looks_blocked(body_text):
        raise LookupBlocked(
            f"Page at {source_url} looks like a bot-detection challenge or block page "
            f"({len(body_text.strip())} chars of content) — not attempting extraction."
        )

    match = re.search(r"Status\t([^\t\n]+)", body_text)
    raw_value = match.group(1).strip() if match else ""
    status = _map_status(raw_value) if raw_value else StatusEnum.unknown
    confidence = 0.95 if raw_value and status != StatusEnum.unknown else 0.4

    return LookupResult(
        status=status,
        source_url=source_url,
        raw_extract=body_text[:4000],
        confidence=confidence,
        screenshot_path=None,
    )


def lookup(company_name: str, entity_number: str = None, ein: str = None) -> LookupResult:
    log.info(f"  [colorado] searching '{company_name}' on Colorado SOS Business Database Search")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(SEARCH_URL, timeout=30000)
            settle(page)
            page.fill("#searchCriteria", company_name)
            page.click("input[type=submit][value=Search]")
            settle(page)
            page.wait_for_timeout(3000)

            body_text = page.inner_text("body")
            if page_looks_blocked(body_text):
                raise LookupBlocked(
                    f"Page at {page.url} looks like a bot-detection challenge or block page "
                    f"({len(body_text.strip())} chars of content) — not attempting extraction."
                )

            matches = _find_matching_rows(page, company_name)
            if not matches:
                raise LookupNotFound(f"No match for '{company_name}' on Colorado SOS Business Search")

            exact = [m for m in matches if m["exact"]]
            candidates = exact if exact else matches
            if len(candidates) > 1:
                base_url = page.url
                resolved = [{"name": m["name"], "href": urljoin(base_url, m["href"])} for m in candidates]
                raise MultipleMatchesFound(resolved)

            href = urljoin(page.url, candidates[0]["href"])
            page.goto(href, timeout=30000)
            settle(page)
            page.wait_for_timeout(2000)
            return _extract_from_detail(page, company_name)
        finally:
            browser.close()


def lookup_detail_url(detail_url: str, entity_name: str) -> LookupResult:
    """Used for a specific sub-entity discovered via a MultipleMatchesFound result."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(detail_url, timeout=30000)
            settle(page)
            page.wait_for_timeout(2000)
            return _extract_from_detail(page, entity_name)
        finally:
            browser.close()
