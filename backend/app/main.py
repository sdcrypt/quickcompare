"""
Entry point for the QuickCompare backend.

This is the first file FastAPI loads when the backend container starts.
It does three things before handling any requests:

    1. Creates all database tables that don't exist yet.
       (Safe to run every time — it won't touch tables that already exist.)

    2. Adds CORS middleware so the frontend running on port 5173 is allowed
       to talk to this API. Without this, the browser would block requests.

    3. Registers all the API routes under the /api prefix.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.db.migrate import run_migrations
from app.db.session import Base, engine

# Auto-create any missing tables on startup (products, scrape_logs).
# If the tables already exist this does nothing, so it is safe to call every time.
Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="QuickCompare API")

# Allow the React frontend (running on port 5173) to make API calls.
# Without this the browser enforces same-origin policy and blocks everything.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    """
    Health check endpoint.

    Visiting the root URL just confirms the API is up and running.
    Also used by the Docker healthcheck in docker-compose.yml.
    """
    return {"message": "QuickCompare API is running"}
