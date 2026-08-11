"""
Celery worker — the background process that runs all scrapers.

This file lives in the 'scraper' Docker container and runs continuously,
waiting for jobs to appear in the Redis queue. When the backend sends a
"scrape this product" task, this worker picks it up and does the actual work.

How it fits into the bigger picture:
    Backend  →  drops a task into Redis  →  this worker picks it up
             →  runs the right scraper   →  saves products to the database
             →  updates scrape_logs so the frontend knows the job is done

Adding a new platform:
    1. Create a new scraper file (e.g. instamart.py) with a scrape_search() function.
    2. Add a 3-line task at the bottom of this file following the same pattern
       as scrape_blinkit and scrape_zepto below.
    3. That's it — the shared _run_scrape() helper handles all the DB work.

Task names must match exactly what the backend sends in send_task(...).
If they don't match, the task sits in the queue forever and nothing happens.
"""

import asyncio
import os
import sys
from datetime import datetime

# Celery prefork workers may not have /app on sys.path — ensure scraper modules resolve.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from blinkit import scrape_search as blinkit_scrape_search
from zepto import scrape_search as zepto_scrape_search
from relevance import filter_relevant

from celery import Celery
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

REDIS_URL    = os.getenv("REDIS_URL",    "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL")

# Celery app — connects to Redis to receive tasks
app = Celery("quickcompare", broker=REDIS_URL, backend=REDIS_URL)

# Direct database connection for this worker process
engine       = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


# ── Platform tasks ────────────────────────────────────────────────────────────
# Each task is just a thin wrapper that imports the right scraper and calls
# the shared _run_scrape() helper. All the heavy lifting is done there.

@app.task(name="scraper.worker.scrape_blinkit")
def scrape_blinkit(query: str, job_id: str):
    """
    Background task: scrape Blinkit for 'query' and save the results.

    Called automatically by Celery — do not call this directly.
    The job_id links back to a row in scrape_logs so the frontend can
    track progress.
    """
    try:
        _run_scrape(query, job_id, blinkit_scrape_search, platform="blinkit")
    except Exception as exc:
        _mark_job_failed(job_id, exc)
        raise


@app.task(name="scraper.worker.scrape_zepto")
def scrape_zepto(query: str, job_id: str):
    """
    Background task: scrape Zepto for 'query' and save the results.

    Called automatically by Celery — do not call this directly.
    Follows the exact same flow as scrape_blinkit, just uses the
    Zepto scraper instead.
    """
    try:
        _run_scrape(query, job_id, zepto_scrape_search, platform="zepto")
    except Exception as exc:
        _mark_job_failed(job_id, exc)
        raise


# ── Shared scrape runner ──────────────────────────────────────────────────────

def _run_scrape(query: str, job_id: str, scraper_fn, platform: str):
    """
    Shared logic that every platform task uses.

    Steps:
        1. Mark the job as "running" so the frontend shows a loading state.
        2. Call the platform's scrape_search() function to collect products.
        3. Save every product to the 'products' table.
        4. Mark the job as "completed" with the count of products saved.

    If anything fails at any step, the error is caught, any half-written
    data is rolled back, and the job is marked "failed" with the error
    message so the frontend can show something useful.

    Args:
        query      - The product the user searched for, e.g. "amul milk".
        job_id     - The unique tracking ID for this job.
        scraper_fn - The scrape_search() function from the platform module.
        platform   - Human-readable name used in log messages, e.g. "zepto".
    """
    db = SessionLocal()
    try:
        # Step 1: Tell the frontend we've started
        _update_log(db, job_id, status="running")

        # Step 2: Open a browser and collect product data
        raw_products = asyncio.run(scraper_fn(query))
        print(f"[worker:{platform}] collected {len(raw_products)} raw products for '{query}'")

        # Step 2b: Drop products that aren't relevant to the query.
        # e.g. searching "amul milk" should not save Amul Butter or Amul Chocolate.
        products = filter_relevant(raw_products, query)
        print(f"[worker:{platform}] kept {len(products)} relevant products after filtering")

        # Step 3: Save each product to the database
        now = datetime.utcnow()
        for p in products:
            db.execute(
                text("""
                    INSERT INTO products
                        (name, price, mrp, unit, image_url, source_url,
                         search_query, source, in_stock, scraped_at)
                    VALUES
                        (:name, :price, :mrp, :unit, :image_url, :source_url,
                         :search_query, :source, :in_stock, :scraped_at)
                """),
                {**p, "scraped_at": now},
            )

        # Step 4: Mark the job as done
        _update_log(db, job_id, status="completed", items_count=len(products))
        db.commit()

    except Exception as exc:
        # Something went wrong — undo any partial writes and record the error
        db.rollback()
        _update_log(db, job_id, status="failed", error=str(exc))
        db.commit()
        print(f"[worker:{platform}] failed for '{query}': {exc}")
    finally:
        db.close()


# ── DB log helper ─────────────────────────────────────────────────────────────

def _mark_job_failed(job_id: str, exc: Exception):
    """Mark a job failed when the task dies before _run_scrape starts."""
    db = SessionLocal()
    try:
        _update_log(db, job_id, status="failed", error=str(exc))
    finally:
        db.close()


def _update_log(db, job_id: str, **kwargs):
    """
    Update one or more columns in scrape_logs for the given job_id.

    Pass any column name as a keyword argument and it gets updated.
    For example:
        _update_log(db, job_id, status="running")
        _update_log(db, job_id, status="completed", items_count=12)

    finished_at is set automatically when the status is "completed"
    or "failed", so you don't need to pass it explicitly.
    """
    kwargs["finished_at"] = (
        datetime.utcnow()
        if kwargs.get("status") in ("completed", "failed")
        else None
    )
    set_clauses = ", ".join(f"{k} = :{k}" for k in kwargs)
    db.execute(
        text(f"UPDATE scrape_logs SET {set_clauses} WHERE job_id = :job_id"),
        {**kwargs, "job_id": job_id},
    )
    db.commit()
