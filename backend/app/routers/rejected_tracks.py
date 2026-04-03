import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_password_changed
from app.models.canonical_track import CanonicalTrack
from app.models.rejected_track import RejectedTrack
from app.models.user import User

router = APIRouter(prefix="/rejected-tracks", tags=["rejected-tracks"])


class RejectIn(BaseModel):
    canonical_track_id: uuid.UUID
    reason: str = "user_rejected"


class RejectedOut(BaseModel):
    id: uuid.UUID
    canonical_track_id: uuid.UUID
    rejected_by: str
    reason: str
    rejected_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=RejectedOut, status_code=201)
def reject_track(
    body: RejectIn,
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    """Permanently exclude a canonical track from future candidate pools."""
    canonical = db.get(CanonicalTrack, body.canonical_track_id)
    if not canonical:
        raise HTTPException(status_code=404, detail="Track not found")

    existing = (
        db.query(RejectedTrack)
        .filter(RejectedTrack.canonical_track_id == body.canonical_track_id)
        .first()
    )
    if existing:
        return existing

    rejected_by = "user_a" if current_user.platform == "spotify" else "user_b"
    entry = RejectedTrack(
        canonical_track_id=body.canonical_track_id,
        rejected_by=rejected_by,
        reason=body.reason,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=list[RejectedOut])
def list_rejected(
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    return db.query(RejectedTrack).order_by(RejectedTrack.rejected_at.desc()).all()


@router.delete("/{entry_id}", status_code=204)
def un_reject_track(
    entry_id: uuid.UUID,
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    """Remove a rejection so the track can surface again."""
    entry = db.get(RejectedTrack, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(entry)
    db.commit()
