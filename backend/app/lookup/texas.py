import logging
import re
import uuid
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from ..models import StatusEnum
from .base import LookupResult, LookupNotFound, LookupBlocked, MultipleMatchesFound, settle, page_looks_blocked

log = logging.getLogger("texas_adapter")

SEARCH_URL = "https://mycpa.cpa.state.tx.us/coa/Index.html"
SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "backend" / "data" / "screenshots"

STATUS_MAP = {
    "ACTIVE": StatusEnum.active,
    "NOT ACTIVE": StatusEnum.forfeited,
    "FORFEITED RIGHTS": StatusEnum.forfeited,
    "TERMINATED": StatusEnum.forfeited,
    "REVOKED": StatusEnum.forfeited,
    "FRANCHISE TAX ENDED": StatusEnum.forfeited,
}


def _map_status(raw_value: str) -> StatusEnum:
    raw_value = raw_value.strip().upper()
    return STATUS_MAP.get(raw_value, StatusEnum.unknown)


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
    return matches


def _extract_from_current_page(page, entity_label: str) -> LookupResult:
    source_url = page.url
    body_text = page.inner_text("body")

    if page_looks_blocked(body_text):
        raise LookupBlocked(
            f"Page at {source_url} looks like a bot-detection challenge or block page "
            f"({len(body_text.strip())} chars of content) — not attempting extraction."
        )

    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", entity_label.strip())[:40]
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(SCREENSHOT_DIR / f"texas_{safe_name}_{uuid.uuid4().hex[:8]}.png")
    page.screenshot(path=screenshot_path, full_page=True)

    match = re.search(r"Right to Transact Business in Texas:\s*\n\s*([A-Z][A-Z ]*)", body_text)
    raw_value = match.group(1).strip() if match else ""
    status = _map_status(raw_value) if match else StatusEnum.unknown
    confidence = 0.95 if match and status != StatusEnum.unknown else 0.4

    return LookupResult(
        status=status,
        source_url=source_url,
        raw_extract=body_text[:4000],
        confidence=confidence,
        screenshot_path=screenshot_path,
    )


def lookup(company_name: str, entity_number: str = None, ein: str = None) -> LookupResult:
    log.info(f"  [texas] searching '{company_name}' on Comptroller entity search")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(SEARCH_URL, timeout=30000)
            settle(page)
            page.fill("#name", company_name)
            page.click("#submitBtn")
            settle(page)
            page.wait_for_timeout(3000)

            matches = _find_all_matching_links(page, company_name)
            log.info(f"  [texas] {len(matches)} matching link(s) found")

            if len(matches) == 0:
                raise LookupNotFound(f"No match found for '{company_name}' on Texas Comptroller search")
            elif len(matches) > 1:
                base_url = page.url
                resolved = [{"name": m["name"], "href": urljoin(base_url, m["href"])} for m in matches]
                raise MultipleMatchesFound(resolved)

            matches[0]["element"].click()
            settle(page)
            page.wait_for_timeout(3000)

            return _extract_from_current_page(page, company_name)
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
            page.wait_for_timeout(3000)
            return _extract_from_current_page(page, entity_name)
        finally:
            browser.close()
