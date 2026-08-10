"""
Celery worker — the background process that actually runs the scraper.

This file lives in the 'scraper' Docker container and runs continuously,
waiting for jobs to appear in the Redis queue. When the backend sends a
"scrape this product" task, this worker picks it up and does the work.

How it fits into the bigger picture:
    Backend  →  drops a task into Redis  →  this worker picks it up
             →  runs the Blinkit scraper  →  saves products to the database
             →  updates the scrape_logs table so the frontend knows it's done

The task name "scraper.worker.scrape_blinkit" must match exactly what the
backend sends in celery_app.send_task(...). If they don't match, the task
will sit in the queue forever and nothing will happen.
"""

import asyncio
import os
from datetime import datetime

from celery import Celery
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load DATABASE_URL and REDIS_URL from the .env file
load_dotenv()

REDIS_URL    = os.getenv("REDIS_URL",    "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL")

# Set up Celery using Redis as both the message queue and the result store
app = Celery("quickcompare", broker=REDIS_URL, backend=REDIS_URL)

# Set up a direct database connection (separate from the backend's connection)
engine       = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


# ── The main task ─────────────────────────────────────────────────────────────

@app.task(name="scraper.worker.scrape_blinkit")
def scrape_blinkit(query: str, job_id: str):
    """
    Background task: scrape Blinkit for 'query' and save the results.

    This is called automatically by Celery when the backend sends a task.
    It should never be called directly.

    Steps:
        1. Mark the job as "running" in the database.
        2. Run the Blinkit scraper (opens a browser, searches, collects data).
        3. Save each product to the 'products' table.
        4. Mark the job as "completed" with a count of how many items were found.

    If anything goes wrong at any step, the error is caught, logged, and
    the job is marked as "failed" so the frontend can show a helpful message.
    """
    from blinkit import scrape_search  # imported here so the worker starts up faster

    db = SessionLocal()
    try:
        # Tell the frontend we've started
        _update_log(db, job_id, status="running")

        # Open a browser and scrape Blinkit
        products = asyncio.run(scrape_search(query))

        # Save every product to the database
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

        # Mark the job as done and record how many products were saved
        _update_log(db, job_id, status="completed", items_count=len(products))
        db.commit()
        print(f"[worker] scraped {len(products)} products for '{query}'")

    except Exception as exc:
        # Something went wrong — roll back any partial saves and record the error
        db.rollback()
        _update_log(db, job_id, status="failed", error=str(exc))
        db.commit()
        print(f"[worker] failed for '{query}': {exc}")
    finally:
        db.close()


# ── Helper ────────────────────────────────────────────────────────────────────

def _update_log(db, job_id: str, **kwargs):
    """
    Update a row in the scrape_logs table for the given job_id.

    Any keyword argument passed in becomes a column update.
    For example: _update_log(db, job_id, status="running")
    automatically sets finished_at to the current time when the
    status is "completed" or "failed".
    """
    # Set the finish time automatically when the job ends
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
