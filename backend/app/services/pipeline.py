"""
Pipeline orchestrator for Phase 2: Ingestion → Normalization → Matching.
Creates and manages SyncRun records.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.raw_track import RawTrack
from app.models.sync_run import SyncRun
from app.models.user import User
from app.services.ingestion.apple_music import ingest_apple_music
from app.services.ingestion.spotify import ingest_spotify
from app.services.matching import process_raw_track


def run_ingestion_pipeline(
    db: Session,
    user: User,
    triggered_by: str = "manual",
) -> SyncRun:
    """
    Ingest → Normalize → Match for a single user.
    Returns the completed SyncRun.
    """
    run = SyncRun(id=uuid.uuid4(), status="running", triggered_by=triggered_by)
    db.add(run)
    db.commit()

    try:
        # Stage 1: Ingestion
        if user.platform == "spotify":
            ingested = ingest_spotify(db, user.id, run.id)
        else:
            ingested = ingest_apple_music(db, user.id, run.id)

        run.raw_tracks_ingested = ingested
        db.commit()

        # Stage 2+3: Normalize + Match all unmatched raw tracks for this run
        unmatched = (
            db.query(RawTrack)
            .filter(RawTrack.sync_run_id == run.id)
            .all()
        )

        matched = 0
        manual_queue = 0
        for raw in unmatched:
            match = process_raw_track(db, raw)
            if match:
                matched += 1
            else:
                manual_queue += 1

        db.commit()

        # Count distinct canonical tracks touched this run
        from app.models.track_match import TrackMatch
        canonical_ids = (
            db.query(TrackMatch.canonical_track_id)
            .join(RawTrack, TrackMatch.raw_track_id == RawTrack.id)
            .filter(RawTrack.sync_run_id == run.id)
            .distinct()
            .count()
        )

        run.status = "completed"
        run.matched_tracks = matched
        run.manual_review_count = manual_queue
        run.canonical_tracks_total = canonical_ids
        run.completed_at = datetime.now(timezone.utc)
        run.metrics = {
            "ingested": ingested,
            "matched": matched,
            "manual_queue": manual_queue,
            "canonical_tracks": canonical_ids,
        }
        db.commit()

    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise

    return run
