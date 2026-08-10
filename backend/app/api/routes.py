"""
API routes — the three endpoints the frontend talks to.

How the flow works:
    1. Frontend calls GET /api/products?q=amul+milk
       → If we have fresh results in the database, return them immediately.
       → If not, return an empty list so the frontend knows to trigger a scrape.

    2. Frontend calls POST /api/scrape/trigger with {"query": "amul milk"}
       → We create a job record, tell the scraper worker to start, and hand
         back a job_id so the frontend can track progress.

    3. Frontend repeatedly calls GET /api/scrape/status/{job_id}
       → We look up the job record and return its current status.
       → Once status is "completed", the frontend calls step 1 again to get results.

CACHE_TTL_HOURS controls how long scraped data is considered fresh.
After 6 hours the same search will trigger a new scrape.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import get_db
from app.models.product import Product
from app.models.scrape_log import ScrapeLog

router = APIRouter()

CACHE_TTL_HOURS = 6  # reuse scraped data for 6 hours before triggering a fresh scrape


class ScrapeRequest(BaseModel):
    """Shape of the JSON body expected by the trigger endpoint."""
    query: str


@router.get("/products")
def get_products(q: str, db: Session = Depends(get_db)):
    """
    Look up products for a search query from the database.

    Only returns rows that were scraped within the last CACHE_TTL_HOURS hours
    so the data shown to users is never too stale. Results are sorted cheapest
    first so users see the best deal at the top.

    Returns an empty list if nothing was scraped yet (or the cache has expired),
    which signals the frontend to start a fresh scrape.
    """
    cutoff = datetime.utcnow() - timedelta(hours=CACHE_TTL_HOURS)
    products = (
        db.query(Product)
        .filter(
            Product.search_query == q.strip().lower(),
            Product.scraped_at >= cutoff,
        )
        .order_by(Product.price.asc())
        .all()
    )
    return products


@router.post("/scrape/trigger")
def trigger_scrape(body: ScrapeRequest, db: Session = Depends(get_db)):
    """
    Start a background scrape job for the given search query.

    Steps:
        1. Validate that the query isn't empty.
        2. Create a job record in the database with status "pending".
        3. Send the task to the Celery scraper worker via Redis.
        4. Return the job_id immediately so the frontend can poll for progress.

    The actual scraping happens asynchronously in the scraper service —
    this endpoint returns in milliseconds.
    """
    q = body.query.strip().lower()
    if not q:
        raise HTTPException(status_code=400, detail="query must not be empty")

    job_id = str(uuid.uuid4())

    # Save a tracking record before the job even starts
    log = ScrapeLog(job_id=job_id, query=q, status="pending")
    db.add(log)
    db.commit()

    # Drop the task into the Redis queue — the scraper worker picks it up
    celery_app.send_task(
        "scraper.worker.scrape_blinkit",
        args=[q, job_id],
    )

    return {"job_id": job_id, "status": "pending"}


@router.get("/scrape/status/{job_id}")
def scrape_status(job_id: str, db: Session = Depends(get_db)):
    """
    Check how a scrape job is going.

    The frontend calls this every few seconds after triggering a scrape.
    Returns the current status, how many items have been found so far,
    and an error message if something went wrong.

    Raises a 404 if the job_id doesn't exist in the database.
    """
    log = db.query(ScrapeLog).filter(ScrapeLog.job_id == job_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id":      log.job_id,
        "status":      log.status,       # pending | running | completed | failed
        "items_count": log.items_count,
        "error":       log.error,
    }
