"""
Celery client setup for the backend.

Celery is a tool that lets us run tasks in the background without making
the user wait. Think of it like a post office — the backend drops a letter
(a task) into the post box (Redis), and the scraper service picks it up
and does the actual work.

This file only sets up the *sending* side. The backend never runs the
scraper itself — it just tells the scraper worker what to do.
Redis is used as the message broker (the post box).
"""

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# The backend uses this object only to send tasks, not to execute them.
# The scraper service (worker.py) has its own Celery setup and actually runs the tasks.
celery_app = Celery(
    "quickcompare",
    broker=REDIS_URL,   # where tasks are queued (Redis)
    backend=REDIS_URL,  # where task results are stored
)
