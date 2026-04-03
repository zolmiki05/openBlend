import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_password_changed
from app.models.canonical_track import CanonicalTrack
from app.models.playlist import Playlist, PlaylistTrack
from app.models.user import User

router = APIRouter(prefix="/playlist", tags=["playlist"])


class TrackOut(BaseModel):
    canonical_track_id: uuid.UUID
    display_title: str
    display_artists: list[str]
    album_art_url: str | None
    bucket: str
    position: int
    score_a: float
    score_b: float
    platform_track_id: str
    llm_explanation: str | None
    validation_status: str | None

    model_config = {"from_attributes": True}


class PlaylistOut(BaseModel):
    id: uuid.UUID
    platform: str
    platform_playlist_id: str
    name: str
    track_count: int
    publish_status: str
    tracks: list[TrackOut]

    model_config = {"from_attributes": True}


@router.get("/current", response_model=list[PlaylistOut])
def get_current_playlists(
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    """Return the most recent published playlist for each platform."""
    result = []
    for platform in ("spotify", "apple_music"):
        playlist = (
            db.query(Playlist)
            .filter(Playlist.platform == platform, Playlist.publish_status == "published")
            .order_by(Playlist.published_at.desc())
            .first()
        )
        if not playlist:
            continue

        tracks_out = []
        for pt in playlist.tracks:
            canonical = db.get(CanonicalTrack, pt.canonical_track_id)
            if canonical:
                tracks_out.append(TrackOut(
                    canonical_track_id=pt.canonical_track_id,
                    display_title=canonical.display_title,
                    display_artists=canonical.display_artists,
                    album_art_url=canonical.album_art_url,
                    bucket=pt.bucket,
                    position=pt.position,
                    score_a=pt.score_a,
                    score_b=pt.score_b,
                    platform_track_id=pt.platform_track_id,
                    llm_explanation=pt.llm_explanation,
                    validation_status=pt.validation_status,
                ))

        result.append(PlaylistOut(
            id=playlist.id,
            platform=playlist.platform,
            platform_playlist_id=playlist.platform_playlist_id,
            name=playlist.name,
            track_count=playlist.track_count,
            publish_status=playlist.publish_status,
            tracks=tracks_out,
        ))
    return result


@router.get("/stats")
def get_playlist_stats(
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    """Bucket breakdown of the latest playlist."""
    playlist = (
        db.query(Playlist)
        .filter(Playlist.publish_status == "published")
        .order_by(Playlist.published_at.desc())
        .first()
    )
    if not playlist:
        return {"total": 0, "buckets": {}}

    buckets: dict[str, int] = {}
    for pt in playlist.tracks:
        buckets[pt.bucket] = buckets.get(pt.bucket, 0) + 1

    return {
        "total": playlist.track_count,
        "platform": playlist.platform,
        "published_at": playlist.published_at,
        "buckets": buckets,
    }
