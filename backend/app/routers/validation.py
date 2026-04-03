import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_password_changed
from app.models.manual_review import ManualReviewQueue
from app.models.raw_track import RawTrack
from app.models.track_match import TrackMatch
from app.models.user import User

router = APIRouter(prefix="/validation", tags=["validation"])


class ReviewItemOut(BaseModel):
    id: uuid.UUID
    raw_track_id: uuid.UUID
    title: str | None
    artists: list[str]
    platform: str | None
    reason: str
    status: str
    confidence: float | None
    created_at: datetime
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("/queue", response_model=list[ReviewItemOut])
def get_review_queue(
    status: str | None = Query(None, pattern="^(pending|approved|rejected)$"),
    limit: int = Query(50, le=200),
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    """Return items in the manual review queue, optionally filtered by status."""
    q = db.query(ManualReviewQueue).order_by(ManualReviewQueue.created_at.desc())
    if status:
        q = q.filter(ManualReviewQueue.status == status)
    items = q.limit(limit).all()

    result = []
    for item in items:
        raw: RawTrack | None = db.get(RawTrack, item.raw_track_id)
        match: TrackMatch | None = (
            db.query(TrackMatch)
            .filter(TrackMatch.raw_track_id == item.raw_track_id)
            .first()
        )
        result.append(ReviewItemOut(
            id=item.id,
            raw_track_id=item.raw_track_id,
            title=raw.title if raw else None,
            artists=raw.artists if raw else [],
            platform=raw.platform if raw else None,
            reason=item.reason,
            status=item.status,
            confidence=match.confidence if match else None,
            created_at=item.created_at,
            reviewed_at=item.reviewed_at,
        ))
    return result


@router.patch("/queue/{item_id}")
def review_item(
    item_id: uuid.UUID,
    action: str = Query(..., pattern="^(approved|rejected)$"),
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    """Mark a review queue item as approved or rejected."""
    item = db.get(ManualReviewQueue, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail="Item already reviewed")

    item.status = action
    item.reviewed_at = datetime.utcnow()
    item.reviewed_by = current_user.username
    db.commit()
    return {"id": item_id, "status": action}
