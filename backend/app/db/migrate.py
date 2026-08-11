"""
Lightweight schema patches for existing databases.

SQLAlchemy's create_all() creates new tables but does not alter existing ones.
When a column is added to a model, run the matching patch here so Docker
volumes with old schemas stay in sync.
"""

from sqlalchemy import inspect, text

from app.db.session import engine


def run_migrations() -> None:
    inspector = inspect(engine)
    if "scrape_logs" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("scrape_logs")}
    if "platform" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE scrape_logs "
                    "ADD COLUMN platform VARCHAR DEFAULT 'unknown'"
                )
            )
