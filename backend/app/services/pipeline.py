"""
Pipeline orchestrator for Phase 2: Ingestion → Enrichment → Normalization → Matching.
Creates and manages SyncRun records.

The pipeline can be triggered for a single user (ingest that user's platform data),
or for both users at once (full run: ingest both + cross-platform enrichment).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.raw_track import RawTrack
from app.models.sync_run import SyncRun
from app.models.user import User
from app.services.ingestion.apple_music import ingest_apple_music
from app.services.ingestion.enrichment import enrich_apple_tracks_with_spotify_features
from app.services.ingestion.spotify import ingest_spotify
from app.services.matching import process_raw_track


def _find_other_user(db: Session, current_user: User) -> User | None:
    """Return the other user in the system (opposite platform)."""
    target_platform = "spotify" if current_user.platform == "apple_music" else "apple_music"
    return db.query(User).filter(User.platform == target_platform).first()


def run_ingestion_pipeline(
    db: Session,
    user: User,
    triggered_by: str = "manual",
) -> SyncRun:
    """
    Full pipeline for one user:
      1. Ingest that user's platform data
      2. If Apple Music user — enrich tracks with Spotify audio features (using Spotify user's token)
      3. Normalize + match all ingested raw tracks

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

        # Stage 1b: Enrich Apple Music tracks with Spotify audio features
        enriched = 0
        if user.platform == "apple_music":
            spotify_user = _find_other_user(db, user)
            if spotify_user:
                enriched = enrich_apple_tracks_with_spotify_features(
                    db, spotify_user.id, run.id
                )

        # Stage 2+3: Normalize + Match all raw tracks for this run
        raw_tracks = (
            db.query(RawTrack)
            .filter(RawTrack.sync_run_id == run.id)
            .all()
        )

        matched = 0
        manual_queue = 0
        for raw in raw_tracks:
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
            "enriched_with_spotify_features": enriched,
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
