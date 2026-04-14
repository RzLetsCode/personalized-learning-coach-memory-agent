"""
Production-Grade Database Session Manager
Enterprise AI Learning Coach - Multi-Tier Memory System

Author: Enterprise AI Architect
Stack: SQLAlchemy + SQLite (dev) / PostgreSQL (prod)
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./learning_coach.db")

# ---------------------------------------------------------------------------
# Engine
# For SQLite: check_same_thread=False is required (Streamlit runs in threads)
# For PostgreSQL: remove connect_args and StaticPool overrides
# ---------------------------------------------------------------------------
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        echo=False,
    )

# ---------------------------------------------------------------------------
# Session Factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ---------------------------------------------------------------------------
# Declarative Base (shared across all models)
# ---------------------------------------------------------------------------
Base = declarative_base()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_db():
    """
    Yield a SQLAlchemy session.
    Use as a context manager or FastAPI dependency.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """
    Return a plain session (for use outside FastAPI dependency injection,
    e.g., directly inside LangGraph nodes or Streamlit callbacks).
    Always close manually after use.
    """
    return SessionLocal()


def init_db():
    """
    Create all tables defined in models if they do not already exist.
    Call once at app startup (e.g., in app.py before launching Streamlit).
    """
    from backend.database import models  # noqa: F401 — registers models with Base
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables initialised successfully.")
