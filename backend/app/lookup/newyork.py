"""NY's entity search (apps.dos.ny.gov) sits behind F5 Distributed Cloud bot defense,
which blocks plain Playwright (headless or headed, bundled Chromium or real Chrome
channel, with or without stealth args) — confirmed by hand before writing this adapter.
Routes through ScrapingBee's stealth_proxy instead, which does get past it. No local
browser is launched here at all; the search is driven via ScrapingBee's js_scenario
(fill/click instructions run in ScrapingBee's own browser), and the final rendered
HTML is parsed for the results table.
"""
import html.parser
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from ..config import SCRAPINGBEE_API_KEY
from ..models import StatusEnum
from .base import LookupResult, LookupNotFound, LookupBlocked, MultipleMatchesFound

log = logging.getLogger("newyork_adapter")

SEARCH_URL = "https://apps.dos.ny.gov/publicInquiry/"
SCRAPINGBEE_ENDPOINT = "https://app.scrapingbee.com/api/v1/"

# id -> substrings of the company name that imply this entity type checkbox.
# Checked in order; first match wins. If nothing matches, all four are selected so the
# search isn't accidentally narrowed to the wrong type.
ENTITY_TYPE_CHECKBOXES = [
    ("LimitedLiabilityPartnership", ["LLP", "L.L.P."]),
    ("LimitedPartnership", ["LP", "L.P."]),
    ("LimitedLiabilityCompany", ["LLC", "L.L.C."]),
    ("Corporation", ["CORP", "CORPORATION", "INC", "INCORPORATED", "PC", "P.C."]),
]

SUFFIX_STRIP_RE = re.compile(
    r"[,\s]+(L\.?L\.?C\.?|L\.?L\.?P\.?|L\.?P\.?|CORP(?:ORATION)?\.?|INC(?:ORPORATED)?\.?|P\.?C\.?)$",
    re.IGNORECASE,
)

STATUS_PREFIX_MAP = [
    ("ACTIVE", StatusEnum.active),
    ("SUSPENDED", StatusEnum.suspended),
    ("INACTIVE", StatusEnum.forfeited),
]


class _ResultTableParser(html.parser.HTMLParser):
    """Pulls header/row text out of the (single) results <table> in the page,
    ignoring nested <span> wrappers around each cell's text."""

    def __init__(self):
        super().__init__()
        self.headers = []
        self.rows = []
        self._in_thead = False
        self._in_tbody = False
        self._in_cell = False
        self._buffer = ""
        self._current_row = []

    def handle_starttag(self, tag, attrs):
        if tag == "thead":
            self._in_thead = True
        elif tag == "tbody":
            self._in_tbody = True
            self._in_thead = False
        elif tag == "tr":
            self._current_row = []
        elif tag in ("th", "td"):
            self._in_cell = True
            self._buffer = ""

    def handle_endtag(self, tag):
        if tag == "th" and self._in_thead:
            self.headers.append(self._buffer.strip())
            self._in_cell = False
        elif tag == "td":
            self._current_row.append(self._buffer.strip())
            self._in_cell = False
        elif tag == "tr" and self._in_tbody and self._current_row:
            self.rows.append(self._current_row)
        elif tag == "tbody":
            self._in_tbody = False

    def handle_data(self, data):
        if self._in_cell:
            self._buffer += data


def _map_status(raw_value: str) -> StatusEnum:
    raw_value = raw_value.strip().upper()
    for prefix, status in STATUS_PREFIX_MAP:
        if raw_value.startswith(prefix):
            return status
    return StatusEnum.unknown


def _normalize_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", name.upper()).strip()


def _base_search_term(company_name: str) -> str:
    stripped = SUFFIX_STRIP_RE.sub("", company_name.strip())
    return stripped if stripped else company_name.strip()


def _checkbox_ids_for(company_name: str) -> list[str]:
    upper = company_name.upper()
    for checkbox_id, needles in ENTITY_TYPE_CHECKBOXES:
        if any(n in upper for n in needles):
            return [checkbox_id]
    return [cid for cid, _ in ENTITY_TYPE_CHECKBOXES]


def _js_set_select(selector: str, value: str) -> dict:
    return {
        "evaluate": (
            f"document.querySelector('{selector}').value='{value}';"
            f"document.querySelector('{selector}').dispatchEvent(new Event('change'));"
        )
    }


def _fetch_rendered_html(search_by: str, search_value: str, checkbox_ids: list[str]) -> str:
    if not SCRAPINGBEE_API_KEY:
        raise LookupBlocked("SCRAPINGBEE_API_KEY not set — can't reach apps.dos.ny.gov (blocked for plain Playwright)")

    instructions = [
        _js_set_select("#searchBy", search_by),
        {"fill": ["#entityname", search_value]},
        _js_set_select("#nameType", "0"),  # AllStatuses
    ]
    if search_by == "EntityName":
        instructions.append(_js_set_select("#searchFunctionality", "3"))  # BeginsWith
        for checkbox_id in checkbox_ids:
            instructions.append({"click": f"#{checkbox_id}"})
        instructions.append({"wait": 500})
    instructions.append({
        "evaluate": "[...document.querySelectorAll('button')].find(b => b.textContent.includes('Search the Database')).click();"
    })
    instructions.append({"wait": 5000})

    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": SEARCH_URL,
        "render_js": "true",
        "stealth_proxy": "true",
        "wait": "3000",
        "country_code": "us",
        "js_scenario": json.dumps({"instructions": instructions}),
    }
    qs = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{SCRAPINGBEE_ENDPOINT}?{qs}")
    try:
        with urllib.request.urlopen(request, timeout=90) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise LookupBlocked(f"ScrapingBee request failed ({e.code}): {body[:500]}")


def _parse_rows(rendered_html: str) -> list[dict]:
    parser = _ResultTableParser()
    parser.feed(rendered_html)
    if not parser.headers:
        # Real page never loaded (still on the bot-defense challenge, or ScrapingBee
        # got blocked too) — don't attempt extraction on a page that isn't the app.
        raise LookupBlocked(
            "No results table found in rendered page — the search form/results never "
            "loaded (WAF challenge page, most likely)."
        )
    return [dict(zip(parser.headers, row)) for row in parser.rows if len(row) == len(parser.headers)]


def _extract_result(row: dict, source_url: str) -> LookupResult:
    raw_value = row.get("Status", "")
    status = _map_status(raw_value) if raw_value else StatusEnum.unknown
    confidence = 0.95 if raw_value and status != StatusEnum.unknown else 0.4

    return LookupResult(
        status=status,
        source_url=source_url,
        raw_extract=str(row),
        confidence=confidence,
        screenshot_path=None,
    )


def lookup(company_name: str, entity_number: str = None, ein: str = None) -> LookupResult:
    log.info(f"  [newyork] searching '{company_name}' on Department of State entity search (via ScrapingBee)")
    rendered_html = _fetch_rendered_html("EntityName", _base_search_term(company_name), _checkbox_ids_for(company_name))
    rows = _parse_rows(rendered_html)
    if not rows:
        raise LookupNotFound(f"No results for '{company_name}' on NY Dept of State search")

    needle = _normalize_name(company_name)
    exact = [r for r in rows if _normalize_name(r.get("Name", "")) == needle]
    if len(exact) == 1:
        return _extract_result(exact[0], SEARCH_URL)

    candidates = exact if len(exact) > 1 else [r for r in rows if needle in _normalize_name(r.get("Name", ""))]
    if not candidates:
        raise LookupNotFound(f"No match for '{company_name}' in NY Dept of State results")
    if len(candidates) == 1:
        return _extract_result(candidates[0], SEARCH_URL)

    matches = [{"name": r["Name"], "href": r.get("DOS ID #", "")} for r in candidates]
    raise MultipleMatchesFound(matches)


def lookup_detail_url(dos_id: str, entity_name: str) -> LookupResult:
    """Used for a specific sub-entity discovered via a MultipleMatchesFound result.
    NY's result grid has no independently-navigable link per row, so the match's
    DOS ID # is carried as the identifier instead of a URL — re-searching by DOS ID
    lands directly on that single entity's row."""
    log.info(f"  [newyork] re-searching by DOS ID '{dos_id}' for '{entity_name}' (via ScrapingBee)")
    rendered_html = _fetch_rendered_html("DOS ID", dos_id, [])
    rows = _parse_rows(rendered_html)
    if len(rows) != 1:
        raise LookupNotFound(f"DOS ID '{dos_id}' did not resolve to exactly one row ({len(rows)} found)")
    return _extract_result(rows[0], SEARCH_URL)
