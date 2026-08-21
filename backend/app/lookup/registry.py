from . import texas
from . import newyork
from . import illinois
from . import colorado
from . import massachusetts

# Each entry: (search_fn, detail_url_fn). detail_url_fn is used to check a
# specific sub-entity discovered via a MultipleMatchesFound result, going
# straight to its known page instead of re-running the ambiguous name search.
# Illinois has no name search at all (ID-only lookup) so it can never raise
# MultipleMatchesFound — no detail_url_fn needed.
LOOKUP_REGISTRY = {
    "Texas": (texas.lookup, texas.lookup_detail_url),
    "New York": (newyork.lookup, newyork.lookup_detail_url),
    "Illinois": (illinois.lookup, None),
    "Colorado": (colorado.lookup, colorado.lookup_detail_url),
    "Massachusetts": (massachusetts.lookup, massachusetts.lookup_detail_url),
}


def get_lookup_fn(state: str):
    entry = LOOKUP_REGISTRY.get(state)
    return entry[0] if entry else None


def get_detail_lookup_fn(state: str):
    entry = LOOKUP_REGISTRY.get(state)
    return entry[1] if entry else None
