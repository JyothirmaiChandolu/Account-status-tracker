import os

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .logsetup import configure_logging
configure_logging()

from .database import get_session, Base, engine
from .models import Company, StatusCheck, TaxAuthority, StatusEnum
from .schemas import (
    StateOut,
    CompanyCreate,
    CompanyListItem,
    CompanyDetail,
    StatusCheckOut,
    StatsOut,
)
from .engine import perform_status_check
from .lookup.generic import SCREENSHOT_DIR
from .seed import seed_tax_authorities

Base.metadata.create_all(bind=engine)
seed_tax_authorities()

app = FastAPI(title="Franchise Tax Account Status Monitoring API")

DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]
extra_origin = os.getenv("FRONTEND_ORIGIN")
allow_origins = DEFAULT_ORIGINS + ([extra_origin] if extra_origin else [])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOT_DIR)), name="screenshots")


def _screenshot_url(path):
    if not path:
        return None
    return f"/screenshots/{os.path.basename(path)}"


def _latest_check(session: Session, company_id: int):
    return (
        session.query(StatusCheck)
        .filter_by(company_id=company_id)
        .order_by(StatusCheck.checked_at.desc())
        .first()
    )


def _visible_companies(session: Session):
    """Excludes anchor rows that turned out to match multiple entities — those
    live on only as the parent_group tag on the real (child) entities that got
    tracked instead, never as a standalone row (even if they carry stale checks
    from before the split was discovered)."""
    companies = session.query(Company).order_by(Company.name).all()
    parent_group_names = {c.parent_group for c in companies if c.parent_group}
    return [c for c in companies if c.name not in parent_group_names]


def _company_list_item(session: Session, c: Company) -> CompanyListItem:
    latest = _latest_check(session, c.id)
    return CompanyListItem(
        id=c.id,
        name=c.name,
        state=c.state,
        entity_number=c.entity_number,
        parent_group=c.parent_group,
        latest_status=latest.status.value if latest else None,
        latest_checked_at=latest.checked_at if latest else None,
        latest_source_url=latest.source_url if latest else None,
    )


def _status_check_out(chk: StatusCheck) -> StatusCheckOut:
    return StatusCheckOut(
        id=chk.id,
        status=chk.status.value,
        checked_at=chk.checked_at,
        source_url=chk.source_url,
        screenshot_url=_screenshot_url(chk.screenshot_path),
        raw_extract=chk.raw_extract,
    )


def _needs_review(c: Company, session: Session) -> bool:
    latest = _latest_check(session, c.id)
    return latest is not None and latest.status == StatusEnum.manual_review_needed


@app.get("/api/states", response_model=list[StateOut])
def list_states(session: Session = Depends(get_session)):
    rows = session.query(TaxAuthority).order_by(TaxAuthority.state).all()
    return [
        StateOut(
            state=r.state,
            authority_name=r.authority_name,
            website=r.website,
            franchise_tax_note=r.franchise_tax_note,
        )
        for r in rows
    ]


@app.get("/api/companies", response_model=list[CompanyListItem])
def list_companies(session: Session = Depends(get_session)):
    return [_company_list_item(session, c) for c in _visible_companies(session)]


@app.get("/api/groups/{group_name}", response_model=list[CompanyListItem])
def get_group_members(group_name: str, session: Session = Depends(get_session)):
    members = session.query(Company).filter_by(parent_group=group_name).order_by(Company.name).all()
    if not members:
        raise HTTPException(404, "Group not found")
    return [_company_list_item(session, c) for c in members]


@app.delete("/api/groups/{group_name}")
def delete_group(group_name: str, session: Session = Depends(get_session)):
    members = session.query(Company).filter_by(parent_group=group_name).all()
    if not members:
        raise HTTPException(404, "Group not found")

    count = 0
    for m in members:
        session.query(StatusCheck).filter_by(company_id=m.id).delete()
        session.delete(m)
        count += 1
    session.commit()
    return {"deleted_count": count}


@app.post("/api/companies", response_model=list[CompanyListItem], status_code=201)
def create_company(payload: CompanyCreate, session: Session = Depends(get_session)):
    authority = session.query(TaxAuthority).filter_by(state=payload.state).first()
    if authority is None:
        raise HTTPException(400, f"Unknown state '{payload.state}'")

    existing = session.query(Company).filter_by(name=payload.name, state=payload.state).first()
    if existing is not None:
        raise HTTPException(409, "Company already exists for this state")

    company = Company(
        name=payload.name,
        state=payload.state,
        entity_number=payload.entity_number,
        ein=payload.ein,
    )
    session.add(company)
    session.commit()

    checks = perform_status_check(session, company)
    affected_company_ids = {chk.company_id for chk in checks}

    if company.id in affected_company_ids:
        return [_company_list_item(session, company)]

    # search matched multiple entities — return each tracked child instead of the anchor
    children = session.query(Company).filter(Company.id.in_(affected_company_ids)).all()
    return [_company_list_item(session, c) for c in children]


@app.get("/api/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int, session: Session = Depends(get_session)):
    company = session.query(Company).filter_by(id=company_id).first()
    if company is None:
        raise HTTPException(404, "Company not found")

    checks = (
        session.query(StatusCheck)
        .filter_by(company_id=company_id)
        .order_by(StatusCheck.checked_at.desc())
        .all()
    )
    return CompanyDetail(
        id=company.id,
        name=company.name,
        state=company.state,
        entity_number=company.entity_number,
        ein=company.ein,
        parent_group=company.parent_group,
        created_at=company.created_at,
        status_checks=[_status_check_out(chk) for chk in checks],
    )


@app.delete("/api/companies/{company_id}", status_code=204)
def delete_company(company_id: int, session: Session = Depends(get_session)):
    company = session.query(Company).filter_by(id=company_id).first()
    if company is None:
        raise HTTPException(404, "Company not found")

    session.query(StatusCheck).filter_by(company_id=company_id).delete()
    session.delete(company)
    session.commit()


@app.post("/api/companies/{company_id}/refresh", response_model=list[StatusCheckOut])
def refresh_company(company_id: int, session: Session = Depends(get_session)):
    company = session.query(Company).filter_by(id=company_id).first()
    if company is None:
        raise HTTPException(404, "Company not found")

    checks = perform_status_check(session, company)
    return [_status_check_out(chk) for chk in checks]


@app.post("/api/companies/refresh-all")
def refresh_all_companies(session: Session = Depends(get_session)):
    companies = _visible_companies(session)
    refreshed = 0
    failed = []
    for c in companies:
        try:
            perform_status_check(session, c)
            refreshed += 1
        except Exception as e:
            failed.append({"company": c.name, "error": str(e)})
    return {"refreshed_count": refreshed, "total": len(companies), "failed": failed}


@app.get("/api/manual-review", response_model=list[CompanyListItem])
def manual_review_queue(session: Session = Depends(get_session)):
    return [_company_list_item(session, c) for c in _visible_companies(session) if _needs_review(c, session)]


@app.get("/api/stats", response_model=StatsOut)
def stats(session: Session = Depends(get_session)):
    companies = _visible_companies(session)
    total = len(companies)
    active_count = 0
    review_count = 0
    states = set()
    for c in companies:
        states.add(c.state)
        latest = _latest_check(session, c.id)
        if latest is None:
            continue
        if latest.status == StatusEnum.active:
            active_count += 1
        if latest.status == StatusEnum.manual_review_needed:
            review_count += 1

    return StatsOut(
        total_companies=total,
        active_count=active_count,
        needs_review_count=review_count,
        states_tracked=len(states),
    )
