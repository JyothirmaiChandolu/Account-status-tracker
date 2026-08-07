from . import texas

# Each entry: (search_fn, detail_url_fn). detail_url_fn is used to check a
# specific sub-entity discovered via a MultipleMatchesFound result, going
# straight to its known page instead of re-running the ambiguous name search.
LOOKUP_REGISTRY = {
    "Texas": (texas.lookup, texas.lookup_detail_url),
}


def get_lookup_fn(state: str):
    entry = LOOKUP_REGISTRY.get(state)
    return entry[0] if entry else None


def get_detail_lookup_fn(state: str):
    entry = LOOKUP_REGISTRY.get(state)
    return entry[1] if entry else None
