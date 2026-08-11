"""
API routes — what the frontend talks to.

Multi-platform flow:
    1. Frontend calls GET /api/products?q=amul+milk
       → Returns whatever is already cached (from any platform).
       → Empty list means nothing is cached yet.

    2. Frontend calls POST /api/scrape/trigger with {"query": "amul milk"}
       → We check which platforms already have fresh cached data.
       → We fire one background Celery task per platform that DOESN'T have cache.
       → Returns a list of jobs: [{"platform": "blinkit", "job_id": "..."}, ...]
       → If every platform is already cached, returns an empty jobs list so the
         frontend knows it can just show the cached results immediately.

    3. Frontend calls GET /api/scrape/status/batch?job_ids=id1,id2
       → Returns the current status of all jobs in one request.
       → Frontend polls this every few seconds until every job is done.
       → Once all jobs are completed (or failed), frontend fetches products again.

Adding a new platform:
    Just add its name to the PLATFORMS list below. As long as a matching
    Celery task "scraper.worker.scrape_<platform>" exists in worker.py,
    everything else wires up automatically.
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

# ── Config ────────────────────────────────────────────────────────────────────

CACHE_TTL_HOURS = 6   # How long scraped data is considered fresh before re-scraping

# Add new platforms here as scrapers are built.
# Each name must match a Celery task: "scraper.worker.scrape_<platform>"
PLATFORMS = ["blinkit", "zepto"]


# ── Request / response schemas ────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    """JSON body that the trigger endpoint expects."""
    query: str


# ── GET /api/products ─────────────────────────────────────────────────────────

@router.get("/products")
def get_products(q: str, db: Session = Depends(get_db)):
    """
    Return all cached products for a search query across every platform.

    Only returns rows scraped within the last CACHE_TTL_HOURS hours so data
    is never too stale. Results from Blinkit and Zepto are returned together,
    sorted cheapest first so the best deal shows at the top.

    Returns an empty list when nothing is cached yet, which tells the frontend
    to call /scrape/trigger to start a fresh scrape.
    """
    cutoff = datetime.utcnow() - timedelta(hours=CACHE_TTL_HOURS)
    return (
        db.query(Product)
        .filter(
            Product.search_query == q.strip().lower(),
            Product.scraped_at   >= cutoff,
        )
        .order_by(Product.price.asc())
        .all()
    )


# ── POST /api/scrape/trigger ──────────────────────────────────────────────────

@router.post("/scrape/trigger")
def trigger_scrape(body: ScrapeRequest, db: Session = Depends(get_db)):
    """
    Start background scrape jobs for every platform that isn't cached yet.

    Smart cache check:
        Before firing any task we check which platforms already have fresh data
        for this query. Only the platforms that are missing or stale get a new
        scrape job. This avoids re-scraping Blinkit if only Zepto is stale.

    Returns:
        {"jobs": [{"platform": "blinkit", "job_id": "..."}, ...]}

        If every platform already has fresh cache, jobs will be an empty list —
        the frontend should just display the existing cached results immediately.
    """
    q = body.query.strip().lower()
    if not q:
        raise HTTPException(status_code=400, detail="query must not be empty")

    cutoff = datetime.utcnow() - timedelta(hours=CACHE_TTL_HOURS)

    # Find which platforms already have fresh data for this query
    cached_platforms = {
        row[0]
        for row in db.query(Product.source)
                     .filter(Product.search_query == q, Product.scraped_at >= cutoff)
                     .distinct()
                     .all()
    }

    jobs = []
    for platform in PLATFORMS:
        if platform in cached_platforms:
            continue  # Already have fresh data — no need to re-scrape

        job_id = str(uuid.uuid4())

        # Create a tracking record before the task even starts
        db.add(ScrapeLog(job_id=job_id, query=q, platform=platform, status="pending"))

        # Fire the Celery task — it runs in the scraper container, not here
        celery_app.send_task(
            f"scraper.worker.scrape_{platform}",
            args=[q, job_id],
        )
        jobs.append({"platform": platform, "job_id": job_id})

    db.commit()
    return {"jobs": jobs}


# ── GET /api/scrape/status/batch ──────────────────────────────────────────────

@router.get("/scrape/status/batch")
def batch_status(job_ids: str, db: Session = Depends(get_db)):
    """
    Return the status of multiple scrape jobs in a single request.

    The frontend passes a comma-separated list of job IDs and gets back
    the current status, platform name, and item count for each one.
    This lets the UI show per-platform progress without making a separate
    HTTP request for every platform.

    Example call:
        GET /api/scrape/status/batch?job_ids=abc-123,def-456

    Returns:
        [
          {"job_id": "abc-123", "platform": "blinkit", "status": "completed", "items_count": 18},
          {"job_id": "def-456", "platform": "zepto",   "status": "running",   "items_count": 0}
        ]
    """
    ids  = [j.strip() for j in job_ids.split(",") if j.strip()]
    logs = db.query(ScrapeLog).filter(ScrapeLog.job_id.in_(ids)).all()
    return [
        {
            "job_id":      log.job_id,
            "platform":    log.platform,
            "status":      log.status,       # pending | running | completed | failed
            "items_count": log.items_count,
            "error":       log.error,
        }
        for log in logs
    ]


# ── GET /api/scrape/status/{job_id} ──────────────────────────────────────────
# Kept for backward compatibility — prefer /status/batch for multi-platform.

@router.get("/scrape/status/{job_id}")
def scrape_status(job_id: str, db: Session = Depends(get_db)):
    """
    Check the status of a single scrape job by its job_id.

    Prefer /scrape/status/batch for checking multiple jobs at once.
    Raises 404 if the job_id doesn't exist.
    """
    log = db.query(ScrapeLog).filter(ScrapeLog.job_id == job_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id":      log.job_id,
        "platform":    log.platform,
        "status":      log.status,
        "items_count": log.items_count,
        "error":       log.error,
    }
