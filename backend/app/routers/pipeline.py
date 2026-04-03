import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_password_changed
from app.models.sync_run import SyncRun
from app.models.user import User
from app.services.pipeline import run_ingestion_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class SyncRunResponse(BaseModel):
    id: uuid.UUID
    status: str
    triggered_by: str
    raw_tracks_ingested: int
    matched_tracks: int
    manual_review_count: int
    canonical_tracks_total: int
    error: str | None
    metrics: dict | None

    model_config = {"from_attributes": True}


@router.post("/ingest", response_model=SyncRunResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_ingestion(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    """Trigger a manual ingestion run for the current user."""
    run = run_ingestion_pipeline(db, current_user, triggered_by="manual")
    return run


@router.get("/runs", response_model=list[SyncRunResponse])
def list_runs(
    current_user: User = Depends(require_password_changed),  # noqa: ARG001 — auth only
    db: Session = Depends(get_db),
    limit: int = 20,
):
    runs = (
        db.query(SyncRun)
        .order_by(SyncRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return runs


@router.get("/runs/{run_id}", response_model=SyncRunResponse)
def get_run(
    run_id: uuid.UUID,
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    run = db.get(SyncRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
