from fastapi import APIRouter
from sqlalchemy import text

from app.db import engine

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    """Unauthenticated liveness probe (checks the database round-trip)."""
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}
