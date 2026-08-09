from sqlalchemy import inspect, text


def run_migrations(engine):
    """Lightweight, idempotent column-add migrations — safe to call on every
    startup, on both SQLite (local) and Postgres (deployed)."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    if "state_adapter_recipes" not in existing_tables:
        return  # table doesn't exist yet — create_all will make it with all columns

    columns = [c["name"] for c in inspector.get_columns("state_adapter_recipes")]
    if "broken_at" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE state_adapter_recipes ADD COLUMN broken_at TIMESTAMP"))
