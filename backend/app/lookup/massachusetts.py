"""Massachusetts' Corporations Division search (corp.sec.state.ma.us) sits behind
Imperva Incapsula. Confirmed by hand: a plain desktop User-Agent alone clears the
initial page load, but the search *submission* still gets blocked (403) through a
headless browser regardless of UA. Headed mode clears it. In production (headless
server, no display) this needs a virtual display — confirmed working under Xvfb in
Docker with `--disable-dev-shm-usage` (default Docker /dev/shm is too small and
Chromium just hangs without it); see Dockerfile's `xvfb-run` wrapper.

There is no free official "status" field at all — confirmed by reading a full real
entity's detail page end to end (Boston Scientific Corporation). The closest signal
is presence of a "Date of Withdrawal:" (foreign entities) or "Date of Dissolution:"
(domestic entities, inferred by naming convention — not yet confirmed against a real
domestic-dissolved example) with an actual date, which only renders when the entity
has left/dissolved; it's simply absent for an active one (confirmed against Toys "R"
Us - Delaware, Inc., withdrawn 12-02-2020). The real "Certificate of Good Standing"
is a separate paid, mail-processed product (1-10 business days) — same category as
New Jersey's — not usable for automated checks.
"""
import logging
import re
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from ..models import StatusEnum
from .base import LookupResult, LookupNotFound, LookupBlocked, MultipleMatchesFound, settle, page_looks_blocked, DESKTOP_USER_AGENT

log = logging.getLogger("massachusetts_adapter")

SEARCH_URL = "https://corp.sec.state.ma.us/corpweb/CorpSearch/CorpSearch.aspx"
TERMINAL_DATE_FIELDS = ("Date of Withdrawal:", "Date of Dissolution:")


def _normalize(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()


def _launch_browser(p):
    # headless=False + a virtual display (Xvfb in production) is the confirmed fix —
    # Incapsula blocks the search POST through headless Chromium regardless of UA.
    return p.chromium.launch(headless=False, args=["--disable-dev-shm-usage"])


def _find_matching_rows(page, company_name: str) -> list[dict]:
    needle = _normalize(company_name)
    matches = []
    for a in page.query_selector_all("a[href*='CorpSummary.aspx']"):
        name = (a.inner_text() or "").strip()
        if not name or needle not in _normalize(name):
            continue
        matches.append({
            "name": name,
            "href": a.get_attribute("href"),
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

    withdrawn_date = None
    for field in TERMINAL_DATE_FIELDS:
        match = re.search(re.escape(field) + r"\s*([0-9]{2}-[0-9]{2}-[0-9]{4})", body_text)
        if match:
            withdrawn_date = match.group(1)
            break

    if withdrawn_date:
        status = StatusEnum.forfeited
        confidence = 0.8
    else:
        status = StatusEnum.active
        confidence = 0.7  # inferred from absence of a terminal-date field, not an explicit status word

    return LookupResult(
        status=status,
        source_url=source_url,
        raw_extract=body_text[:4000],
        confidence=confidence,
        screenshot_path=None,
    )


def lookup(company_name: str, entity_number: str = None, ein: str = None) -> LookupResult:
    log.info(f"  [massachusetts] searching '{company_name}' on MA Corporations Division (headed mode)")
    with sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page(user_agent=DESKTOP_USER_AGENT)
        try:
            page.goto(SEARCH_URL, timeout=30000)
            settle(page)
            page.check("#MainContent_rdoByEntityName")
            page.fill("#MainContent_txtEntityName", company_name)
            page.click("#MainContent_btnSearch")
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
                raise LookupNotFound(f"No match for '{company_name}' on MA Corporations Division search")

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
        browser = _launch_browser(p)
        page = browser.new_page(user_agent=DESKTOP_USER_AGENT)
        try:
            page.goto(detail_url, timeout=30000)
            settle(page)
            page.wait_for_timeout(2000)
            return _extract_from_detail(page, entity_name)
        finally:
            browser.close()
