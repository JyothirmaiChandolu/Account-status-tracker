import sys

from .logsetup import configure_logging
configure_logging()

from .database import SessionLocal
from .models import Company, StatusCheck, TaxAuthority, StateAdapterRecipe
from .lookup.generic import bootstrap_recipe, lookup_with_recipe
from .lookup.base import LookupNotFound, LookupBlocked, MultipleMatchesFound


def run(company_name: str, state: str):
    session = SessionLocal()
    try:
        authority = session.query(TaxAuthority).filter_by(state=state).first()
        if authority is None:
            print(f"No tax authority row for state '{state}'")
            return

        recipe = session.query(StateAdapterRecipe).filter_by(state=state).first()

        if recipe is None:
            print(f"No recipe yet for '{state}' — bootstrapping via LLM...")
            recipe = bootstrap_recipe(state, authority.website, source_script="run_generic_lookup")
            session.add(recipe)
            session.commit()
            print(f"Bootstrapped recipe: search_page_url={recipe.search_page_url}, "
                  f"name_field_selector={recipe.name_field_selector}, submit_selector={recipe.submit_selector}")
        elif recipe.is_broken:
            print(f"Existing recipe for '{state}' marked broken — re-bootstrapping via LLM...")
            fresh = bootstrap_recipe(state, authority.website, source_script="run_generic_lookup")
            recipe.search_page_url = fresh.search_page_url
            recipe.name_field_selector = fresh.name_field_selector
            recipe.submit_selector = fresh.submit_selector
            recipe.has_result_list = fresh.has_result_list
            recipe.status_label_text = fresh.status_label_text
            recipe.status_value_map = fresh.status_value_map or {}
            recipe.is_broken = False
            recipe.version = (recipe.version or 1) + 1
            session.commit()
            print(f"Re-bootstrapped recipe: search_page_url={recipe.search_page_url}, "
                  f"name_field_selector={recipe.name_field_selector}, submit_selector={recipe.submit_selector}")
        else:
            print(f"Reusing existing recipe for '{state}' (version {recipe.version}), no LLM navigation call needed.")

        try:
            result, updated_recipe = lookup_with_recipe(recipe, company_name, source_script="run_generic_lookup")
        except MultipleMatchesFound as e:
            print(f"Search matched {len(e.matches)} distinct entities (not just one) — run this through the "
                  f"dashboard/engine.py to have each tracked separately:")
            for m in e.matches:
                print(f"  {m['name']} -> {m['href']}")
            return
        except (LookupNotFound, LookupBlocked) as e:
            print(f"Lookup failed with existing recipe: {e}")
            print("Re-bootstrapping recipe...")
            fresh = bootstrap_recipe(state, authority.website, source_script="run_generic_lookup_rebootstrap")
            recipe.search_page_url = fresh.search_page_url
            recipe.name_field_selector = fresh.name_field_selector
            recipe.submit_selector = fresh.submit_selector
            recipe.has_result_list = fresh.has_result_list
            recipe.status_label_text = fresh.status_label_text
            recipe.status_value_map = fresh.status_value_map or {}
            recipe.version = (recipe.version or 1) + 1
            result, updated_recipe = lookup_with_recipe(recipe, company_name, source_script="run_generic_lookup")

        session.commit()

        company = session.query(Company).filter_by(name=company_name, state=state).first()
        if company is None:
            company = Company(name=company_name, state=state)
            session.add(company)
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

        print(f"Status: {check.status.value}")
        print(f"Confidence: {check.confidence}")
        print(f"Source URL: {check.source_url}")
        print(f"Screenshot: {check.screenshot_path}")
    finally:
        session.close()


if __name__ == "__main__":
    company_name = sys.argv[1] if len(sys.argv) > 1 else "MHK Tech Inc"
    state = sys.argv[2] if len(sys.argv) > 2 else "Texas"
    run(company_name, state)
