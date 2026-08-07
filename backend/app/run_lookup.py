import sys

from .logsetup import configure_logging
configure_logging()

from .database import SessionLocal
from .models import Company
from .engine import perform_status_check


def main():
    company_name = sys.argv[1] if len(sys.argv) > 1 else "MHK Tech Inc"
    state = sys.argv[2] if len(sys.argv) > 2 else "Texas"

    session = SessionLocal()
    try:
        company = session.query(Company).filter_by(name=company_name, state=state).first()
        if company is None:
            company = Company(name=company_name, state=state)
            session.add(company)
            session.commit()
            print(f"Created new company record: {company.name} ({company.state})")

        checks = perform_status_check(session, company)
        if len(checks) > 1 or checks[0].company_id != company.id:
            print(f"Search matched {len(checks)} distinct entities — tracked separately under parent_group='{company.name}':")
            for chk in checks:
                print(f"  {chk.company.name}: {chk.status.value} (confidence {chk.confidence})")
        else:
            check = checks[0]
            print(f"Status: {check.status.value}")
            print(f"Confidence: {check.confidence}")
            print(f"Source URL: {check.source_url}")
            print(f"Screenshot: {check.screenshot_path}")
            print(f"Checked at: {check.checked_at}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
