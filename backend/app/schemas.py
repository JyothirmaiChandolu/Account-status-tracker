from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, field_serializer


def _as_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class StateOut(BaseModel):
    state: str
    authority_name: str
    website: str
    franchise_tax_note: Optional[str] = None


class CompanyCreate(BaseModel):
    name: str
    state: str
    entity_number: Optional[str] = None
    ein: Optional[str] = None


class StatusCheckOut(BaseModel):
    id: int
    status: str
    checked_at: datetime
    source_url: Optional[str] = None
    screenshot_url: Optional[str] = None
    raw_extract: Optional[str] = None

    @field_serializer("checked_at")
    def _ser_checked_at(self, dt: datetime, _info):
        return _as_utc_iso(dt)


class CompanyListItem(BaseModel):
    id: int
    name: str
    state: str
    entity_number: Optional[str] = None
    parent_group: Optional[str] = None
    latest_status: Optional[str] = None
    latest_checked_at: Optional[datetime] = None
    latest_source_url: Optional[str] = None

    @field_serializer("latest_checked_at")
    def _ser_latest_checked_at(self, dt: Optional[datetime], _info):
        return _as_utc_iso(dt)


class CompanyDetail(BaseModel):
    id: int
    name: str
    state: str
    entity_number: Optional[str] = None
    ein: Optional[str] = None
    parent_group: Optional[str] = None
    created_at: datetime
    status_checks: list[StatusCheckOut]

    @field_serializer("created_at")
    def _ser_created_at(self, dt: datetime, _info):
        return _as_utc_iso(dt)


class StatsOut(BaseModel):
    total_companies: int
    active_count: int
    needs_review_count: int
    states_tracked: int
