"""
Database connection setup.

This file does three things:
  1. Reads the database address from the environment variable DATABASE_URL.
  2. Creates a connection to PostgreSQL that the whole app shares.
  3. Provides a helper (get_db) that hands a database session to each API
     request and makes sure it gets closed properly when the request is done.

Everything else in the backend imports 'Base' from here so all database
tables are registered in one place.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

# The engine is the actual connection pool to PostgreSQL.
engine = create_engine(DATABASE_URL)

# SessionLocal is a factory — calling it gives you a fresh database session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class every database model inherits from.
# SQLAlchemy uses it to know which tables exist.
Base = declarative_base()


def get_db():
    """
    Open a database session for the duration of a single API request.

    Used as a FastAPI dependency — FastAPI calls this automatically before
    each endpoint runs and closes the session when the endpoint finishes,
    even if something goes wrong.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
