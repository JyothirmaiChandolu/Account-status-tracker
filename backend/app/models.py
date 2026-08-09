import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    JSON,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base


class StatusEnum(str, enum.Enum):
    active = "active"
    delinquent = "delinquent"
    forfeited = "forfeited"
    suspended = "suspended"
    unknown = "unknown"
    manual_review_needed = "manual_review_needed"


class TaxAuthority(Base):
    __tablename__ = "tax_authorities"

    id = Column(Integer, primary_key=True)
    state = Column(String, unique=True, nullable=False, index=True)
    authority_name = Column(String, nullable=False)
    website = Column(String, nullable=False)
    franchise_tax_note = Column(String, nullable=True)

    companies = relationship("Company", back_populates="tax_authority")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    state = Column(String, ForeignKey("tax_authorities.state"), nullable=False)
    entity_number = Column(String, nullable=True)
    ein = Column(String, nullable=True)
    parent_group = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tax_authority = relationship("TaxAuthority", back_populates="companies")
    status_checks = relationship(
        "StatusCheck", back_populates="company", order_by="StatusCheck.checked_at.desc()"
    )


class StatusCheck(Base):
    __tablename__ = "status_checks"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    status = Column(Enum(StatusEnum), nullable=False)
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    source_url = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    screenshot_path = Column(String, nullable=True)
    raw_extract = Column(Text, nullable=True)

    company = relationship("Company", back_populates="status_checks")


class StateAdapterRecipe(Base):
    """LLM-bootstrapped, then deterministically replayed, navigation/extraction recipe per state."""

    __tablename__ = "state_adapter_recipes"

    id = Column(Integer, primary_key=True)
    state = Column(String, unique=True, nullable=False, index=True)
    search_page_url = Column(String, nullable=False)
    name_field_selector = Column(String, nullable=False)
    submit_selector = Column(String, nullable=False)
    has_result_list = Column(Boolean, nullable=False, default=False)
    status_label_text = Column(String, nullable=True)
    status_value_map = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    is_broken = Column(Boolean, nullable=False, default=False)
    broken_at = Column(DateTime(timezone=True), nullable=True)
    last_verified_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LlmCallLog(Base):
    """Append-only log of every LLM call, for cost monitoring across all scripts."""

    __tablename__ = "llm_call_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    source_script = Column(String, nullable=False)
    purpose = Column(String, nullable=True)
    model = Column(String, nullable=False)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
