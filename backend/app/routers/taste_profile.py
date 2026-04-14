"""
Taste profile endpoints.

GET  /taste-profile/scores   — top taste scores for the current user, joined with track info
POST /taste-profile/refresh  — re-run taste scoring only (no ingestion, no publish)
GET  /taste-profile/summary  — aggregate stats (track count, score distribution, platform breakdown)
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_password_changed
from app.models.canonical_track import CanonicalTrack
from app.models.raw_track import RawTrack
from app.models.taste_score import TasteScore
from app.models.track_match import TrackMatch
from app.models.user import User
from app.services.taste_scoring import compute_taste_scores

router = APIRouter(prefix="/taste-profile", tags=["taste_profile"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class TasteScoreItem(BaseModel):
    canonical_track_id: uuid.UUID
    display_title: str
    display_artists: list[str]
    album: str | None
    album_art_url: str | None
    score: float
    max_source_weight: float
    frequency: int
    is_saved: bool
    playlist_count: int
    lastfm_playcount_bonus: float
    # Which platforms contributed raw tracks
    platforms: list[str]
    source_types: list[str]
    computed_at: datetime

    model_config = {"from_attributes": True}


class TasteProfileSummary(BaseModel):
    total_scored_tracks: int
    avg_score: float
    max_score: float
    saved_tracks: int
    lastfm_boosted_tracks: int   # tracks with lastfm_playcount_bonus > 0
    platform_breakdown: dict[str, int]  # platform → raw_track count
    source_type_breakdown: dict[str, int]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/scores", response_model=list[TasteScoreItem])
def get_taste_scores(
    limit: int = Query(default=100, ge=1, le=500),
    sort_by: Literal["score", "frequency", "lastfm"] = Query(default="score"),
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    """Return the user's top taste-scored tracks with full breakdown."""
    scores = (
        db.query(TasteScore)
        .filter(TasteScore.user_id == current_user.id)
        .all()
    )

    if sort_by == "frequency":
        scores.sort(key=lambda s: s.frequency, reverse=True)
    elif sort_by == "lastfm":
        scores.sort(key=lambda s: s.lastfm_playcount_bonus, reverse=True)
    else:
        scores.sort(key=lambda s: s.score, reverse=True)

    scores = scores[:limit]

    # Fetch canonical track info + contributing raw track platforms/sources
    result = []
    for ts in scores:
        ct = db.get(CanonicalTrack, ts.canonical_track_id)
        if not ct:
            continue

        raw_tracks = (
            db.query(RawTrack.platform, RawTrack.source_type)
            .join(TrackMatch, TrackMatch.raw_track_id == RawTrack.id)
            .filter(
                TrackMatch.canonical_track_id == ts.canonical_track_id,
                RawTrack.user_id == current_user.id,
            )
            .all()
        )
        platforms = list({r.platform for r in raw_tracks})
        source_types = list({r.source_type for r in raw_tracks})

        result.append(TasteScoreItem(
            canonical_track_id=ts.canonical_track_id,
            display_title=ct.display_title,
            display_artists=ct.display_artists,
            album=ct.album,
            album_art_url=ct.album_art_url,
            score=round(ts.score, 4),
            max_source_weight=ts.max_source_weight,
            frequency=ts.frequency,
            is_saved=ts.is_saved,
            playlist_count=ts.playlist_count,
            lastfm_playcount_bonus=round(ts.lastfm_playcount_bonus, 4),
            platforms=platforms,
            source_types=source_types,
            computed_at=ts.computed_at,
        ))

    return result


@router.post("/refresh")
def refresh_taste_scores(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    """Re-compute taste scores from existing raw tracks without triggering ingestion."""
    count = compute_taste_scores(db, current_user)
    return {"recomputed": count}


@router.get("/summary", response_model=TasteProfileSummary)
def get_taste_profile_summary(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    scores = (
        db.query(TasteScore)
        .filter(TasteScore.user_id == current_user.id)
        .all()
    )

    if not scores:
        return TasteProfileSummary(
            total_scored_tracks=0, avg_score=0, max_score=0,
            saved_tracks=0, lastfm_boosted_tracks=0,
            platform_breakdown={}, source_type_breakdown={},
        )

    avg_score = sum(s.score for s in scores) / len(scores)
    max_score = max(s.score for s in scores)
    saved = sum(1 for s in scores if s.is_saved)
    lastfm_boosted = sum(1 for s in scores if s.lastfm_playcount_bonus > 0)

    # Platform / source breakdown from raw_tracks
    raw_tracks = (
        db.query(RawTrack.platform, RawTrack.source_type)
        .filter(RawTrack.user_id == current_user.id)
        .all()
    )
    platform_breakdown: dict[str, int] = {}
    source_type_breakdown: dict[str, int] = {}
    for rt in raw_tracks:
        platform_breakdown[rt.platform] = platform_breakdown.get(rt.platform, 0) + 1
        source_type_breakdown[rt.source_type] = source_type_breakdown.get(rt.source_type, 0) + 1

    return TasteProfileSummary(
        total_scored_tracks=len(scores),
        avg_score=round(avg_score, 4),
        max_score=round(max_score, 4),
        saved_tracks=saved,
        lastfm_boosted_tracks=lastfm_boosted,
        platform_breakdown=platform_breakdown,
        source_type_breakdown=source_type_breakdown,
    )
