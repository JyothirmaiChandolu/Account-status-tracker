import csv

from .config import CSV_PATH
from .database import Base, engine, SessionLocal
from .models import TaxAuthority


def seed_tax_authorities():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                state = row["State"].strip()
                existing = session.query(TaxAuthority).filter_by(state=state).first()
                if existing:
                    existing.authority_name = row["Tax Authority"].strip()
                    existing.website = row["Website"].strip()
                    existing.franchise_tax_note = row["Franchise/Privilege Tax?"].strip()
                else:
                    session.add(
                        TaxAuthority(
                            state=state,
                            authority_name=row["Tax Authority"].strip(),
                            website=row["Website"].strip(),
                            franchise_tax_note=row["Franchise/Privilege Tax?"].strip(),
                        )
                    )
        session.commit()
        count = session.query(TaxAuthority).count()
        print(f"Seeded/updated tax_authorities table. Total rows: {count}")
    finally:
        session.close()


if __name__ == "__main__":
    seed_tax_authorities()
