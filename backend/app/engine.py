"""Single entrypoint used by the API/CLI/scheduler: deterministic adapter first,
generic LLM-bootstrapped engine second, manual_review_needed as last resort.
Handles the case where a name search matches multiple distinct entities
(e.g. a parent company with several subsidiary filings) by tracking each
match as its own company row, grouped under the searched name.
"""
import logging
from datetime import datetime, timedelta, timezone

from .models import Company, StatusCheck, StatusEnum, TaxAuthority, StateAdapterRecipe
from .lookup.registry import get_lookup_fn, get_detail_lookup_fn
from .lookup.base import LookupNotFound, LookupBlocked, MultipleMatchesFound
from .lookup.generic import bootstrap_recipe, lookup_with_recipe, lookup_detail_url
from .notifications import maybe_alert_on_status_change

log = logging.getLogger("engine")

# How long to wait before retrying a state whose recipe failed, before trying
# another full LLM bootstrap. Without this, an hourly refresh-all would pay
# for a fresh bootstrap attempt every single hour for a state that's simply
# not automatable (dead server, bot wall) — 24x the cost for no new information.
BROKEN_RETRY_COOLDOWN = timedelta(hours=24)


def _recipe_in_cooldown(recipe: StateAdapterRecipe) -> bool:
    if recipe.broken_at is None:
        return False
    broken_at = recipe.broken_at
    if broken_at.tzinfo is None:
        broken_at = broken_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - broken_at < BROKEN_RETRY_COOLDOWN


def perform_status_check(session, company: Company) -> list[StatusCheck]:
    checks = _perform_status_check_impl(session, company)
    for check in checks:
        maybe_alert_on_status_change(session, check)
    return checks


def _perform_status_check_impl(session, company: Company) -> list[StatusCheck]:
    """Runs a status check for `company`. Normally returns a single-element list.
    If the search matches multiple distinct entities, no check is recorded against
    `company` itself — instead one child Company per match is created (tagged with
    parent_group=company.name) and checked individually; their checks are returned.
    """
    log.info(f"=== Checking '{company.name}' ({company.state}) ===")
    deterministic_fn = get_lookup_fn(company.state)

    if deterministic_fn is not None:
        log.info(f"Using deterministic adapter for {company.state}")
        try:
            result = deterministic_fn(company.name, entity_number=company.entity_number, ein=company.ein)
            log.info(f"Result: {result.status.value} (confidence {result.confidence}) — {result.source_url}")
            if result.discovered_ein and not company.ein:
                log.info(f"Discovered EIN via web search, saving to company record: {result.discovered_ein}")
                company.ein = result.discovered_ein
                session.add(company)
            check = StatusCheck(
                company_id=company.id,
                status=result.status,
                source_url=result.source_url,
                confidence=result.confidence,
                screenshot_path=result.screenshot_path,
                raw_extract=result.raw_extract,
            )
            session.add(check)
            session.commit()
            return [check]
        except MultipleMatchesFound as e:
            log.info(f"Search matched {len(e.matches)} distinct entities — checking each individually")
            detail_fn = get_detail_lookup_fn(company.state)
            return _handle_multi_match(session, company, e.matches, lambda href, name: detail_fn(href, name))
        except (LookupNotFound, LookupBlocked) as e:
            log.info(f"Deterministic adapter failed ({e}) — falling back to generic engine")
        except Exception as e:
            # Covers browser-launch failures (e.g. missing system libraries) and
            # anything else unexpected — never let the deterministic path crash
            # the request; fall back to generic engine, which has its own
            # last-resort manual_review_needed handling.
            log.info(f"Deterministic adapter crashed ({type(e).__name__}: {e}) — falling back to generic engine")

    authority = session.query(TaxAuthority).filter_by(state=company.state).first()
    if authority is None:
        log.info(f"No tax authority on file for '{company.state}' — manual review needed")
        check = StatusCheck(
            company_id=company.id,
            status=StatusEnum.manual_review_needed,
            raw_extract=f"No tax authority on file for state '{company.state}'.",
        )
        session.add(check)
        session.commit()
        return [check]

    recipe = session.query(StateAdapterRecipe).filter_by(state=company.state).first()

    if recipe is not None and recipe.is_broken and _recipe_in_cooldown(recipe):
        log.info(f"Recipe for {company.state} is broken (since {recipe.broken_at}) and still in cooldown "
                 f"— skipping re-bootstrap, marking manual_review_needed without spending LLM cost")
        check = StatusCheck(
            company_id=company.id,
            status=StatusEnum.manual_review_needed,
            source_url=authority.website,
            confidence=0.0,
            raw_extract=f"Automated lookup for {company.state} failed as of {recipe.broken_at}; "
                        f"not retrying again until the cooldown expires.",
        )
        session.add(check)
        session.commit()
        return [check]

    try:
        if recipe is None:
            log.info(f"No saved recipe for {company.state} yet — bootstrapping via LLM (this takes longer, one-time cost)")
            recipe = bootstrap_recipe(company.state, authority.website, source_script="engine")
            session.add(recipe)
            session.commit()
            log.info(f"Bootstrapped: search_page_url={recipe.search_page_url}, "
                     f"name_field={recipe.name_field_selector}, submit={recipe.submit_selector}")
        elif recipe.is_broken:
            log.info(f"Saved recipe for {company.state} marked broken — re-bootstrapping via LLM")
            fresh = bootstrap_recipe(company.state, authority.website, source_script="engine")
            _copy_recipe_fields(recipe, fresh)
            recipe.is_broken = False
            recipe.broken_at = None
            recipe.version = (recipe.version or 1) + 1
            session.commit()
            log.info(f"Re-bootstrapped: search_page_url={recipe.search_page_url}")
        else:
            log.info(f"Reusing saved recipe for {company.state} (version {recipe.version}) — no LLM navigation needed")

        try:
            log.info(f"Searching '{company.name}' at {recipe.search_page_url}")
            result, updated_recipe = lookup_with_recipe(recipe, company.name, source_script="engine")
            log.info(f"Result: {result.status.value} (confidence {result.confidence}) — {result.source_url}")
        except MultipleMatchesFound as e:
            log.info(f"Search matched {len(e.matches)} distinct entities — checking each individually")
            session.commit()  # persist has_result_list flip, if any, before spinning off children
            return _handle_multi_match(
                session, company, e.matches,
                lambda href, name: lookup_detail_url(recipe, href, name, source_script="engine")[0],
            )
        except (LookupNotFound, LookupBlocked) as e:
            log.info(f"Saved recipe failed ({e}) — re-bootstrapping and retrying once")
            fresh = bootstrap_recipe(company.state, authority.website, source_script="engine_rebootstrap")
            _copy_recipe_fields(recipe, fresh)
            recipe.version = (recipe.version or 1) + 1
            try:
                result, updated_recipe = lookup_with_recipe(recipe, company.name, source_script="engine")
                log.info(f"Result: {result.status.value} (confidence {result.confidence}) — {result.source_url}")
            except MultipleMatchesFound as e:
                log.info(f"Search matched {len(e.matches)} distinct entities — checking each individually")
                session.commit()
                return _handle_multi_match(
                    session, company, e.matches,
                    lambda href, name: lookup_detail_url(recipe, href, name, source_script="engine")[0],
                )

        session.commit()
        check = StatusCheck(
            company_id=company.id,
            status=result.status,
            source_url=result.source_url,
            confidence=result.confidence,
            screenshot_path=result.screenshot_path,
            raw_extract=result.raw_extract,
        )
        session.add(check)
        session.commit()
        return [check]

    except Exception as e:
        # Covers LookupNotFound/LookupBlocked as well as anything unexpected
        # (browser timeout, site down, etc.) — never let an automation failure
        # crash the request; always fall back to a manual-review record instead.
        log.info(f"Check failed ({type(e).__name__}: {e}) — marking manual_review_needed")
        session.rollback()
        if recipe is not None and recipe.id is not None:
            recipe.is_broken = True
            recipe.broken_at = datetime.now(timezone.utc)
            session.commit()
        check = StatusCheck(
            company_id=company.id,
            status=StatusEnum.manual_review_needed,
            source_url=authority.website,
            confidence=0.0,
            raw_extract=f"{type(e).__name__}: {e}",
        )
        session.add(check)
        session.commit()
        return [check]


def _handle_multi_match(session, anchor: Company, matches: list, detail_lookup_fn) -> list[StatusCheck]:
    checks = []
    for i, m in enumerate(matches, 1):
        log.info(f"  [{i}/{len(matches)}] Checking '{m['name']}'")
        child = session.query(Company).filter_by(name=m["name"], state=anchor.state).first()
        if child is None:
            child = Company(name=m["name"], state=anchor.state, parent_group=anchor.name)
            session.add(child)
            session.commit()
        elif child.parent_group is None:
            child.parent_group = anchor.name
            session.commit()

        try:
            result = detail_lookup_fn(m["href"], m["name"])
            log.info(f"  [{i}/{len(matches)}] Result: {result.status.value} (confidence {result.confidence})")
            check = StatusCheck(
                company_id=child.id,
                status=result.status,
                source_url=result.source_url,
                confidence=result.confidence,
                screenshot_path=result.screenshot_path,
                raw_extract=result.raw_extract,
            )
        except Exception as e:
            log.info(f"  [{i}/{len(matches)}] Failed ({type(e).__name__}: {e}) — manual_review_needed")
            check = StatusCheck(
                company_id=child.id,
                status=StatusEnum.manual_review_needed,
                source_url=m["href"],
                confidence=0.0,
                raw_extract=str(e),
            )
        session.add(check)
        session.commit()
        checks.append(check)
    return checks


def _copy_recipe_fields(target: StateAdapterRecipe, source: StateAdapterRecipe):
    target.search_page_url = source.search_page_url
    target.name_field_selector = source.name_field_selector
    target.submit_selector = source.submit_selector
    target.has_result_list = source.has_result_list
    target.status_label_text = source.status_label_text
    target.status_value_map = source.status_value_map or {}
