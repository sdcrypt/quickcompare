"""
Scrape job tracking table.

Every time the frontend asks us to scrape a product, we create a row here
before the scrape even starts. The row acts like a ticket — the frontend
uses the job_id to keep asking "are you done yet?" until the scrape
finishes (or fails).

Possible status values:
    pending   - The job was created but the scraper hasn't picked it up yet.
    running   - The scraper is actively browsing Blinkit right now.
    completed - Scraping finished successfully and products were saved.
    failed    - Something went wrong (site blocked us, timeout, etc.).
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.session import Base


class ScrapeLog(Base):
    """
    Tracks one scrape job from start to finish.

    Columns:
        id          - Auto-generated row number.
        job_id      - A unique ID (like a tracking number) that the frontend
                      uses to check progress. Generated automatically.
        query       - The search term that was scraped, e.g. "amul milk".
        status      - Current state of the job: pending, running, completed, or failed.
        started_at  - When the job was created.
        finished_at - When the job ended (either successfully or with an error).
        items_count - How many products were saved after the scrape completed.
        error       - If the scrape failed, the reason is stored here for debugging.
    """

    __tablename__ = "scrape_logs"

    id          = Column(Integer, primary_key=True, index=True)
    job_id      = Column(String, unique=True, index=True,
                         default=lambda: str(uuid.uuid4()))
    query       = Column(String)
    status      = Column(String, default="pending")
    started_at  = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    items_count = Column(Integer, default=0)
    error       = Column(Text, nullable=True)
