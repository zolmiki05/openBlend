"""
Pipeline orchestrator.

Phase 2: Ingestion → Enrichment → Normalization → Matching
Phase 3: Taste Scoring → Candidate Pool → Playlist Composition → Publish
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.canonical_track import CanonicalTrack
from app.models.playlist import Playlist, PlaylistTrack
from app.models.raw_track import RawTrack
from app.models.sync_run import SyncRun
from app.models.user import User
from app.models.user_settings import UserSettings
from app.services.candidate_pool import build_candidate_pool
from app.services.ingestion.apple_music import ingest_apple_music
from app.services.ingestion.enrichment import enrich_apple_tracks_with_spotify_features
from app.services.ingestion.spotify import ingest_spotify
from app.services.matching import process_raw_track
from app.services.playlist_builder import compose_playlist
from app.services.publisher.resolver import resolve_apple_catalog_id, resolve_spotify_id
from app.services.publisher.apple_music import publish_to_apple_music
from app.services.publisher.spotify import publish_to_spotify
from app.services.taste_scoring import compute_taste_scores


def _get_or_create_settings(db: Session, user: User) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    if not settings:
        settings = UserSettings(user_id=user.id)
        db.add(settings)
        db.commit()
    return settings


def _find_user_by_platform(db: Session, platform: str) -> User | None:
    return db.query(User).filter(User.platform == platform).first()


def run_ingestion_pipeline(
    db: Session,
    user: User,
    triggered_by: str = "manual",
) -> SyncRun:
    """
    Full pipeline for one user:
      1. Ingest platform data
      2. Enrich Apple Music tracks with Spotify audio features
      3. Normalize + match raw tracks
      4. Compute taste scores
      5. Build candidate pool (requires both users to have scores)
      6. Compose + publish playlist

    Returns the completed SyncRun.
    """
    run = SyncRun(id=uuid.uuid4(), status="running", triggered_by=triggered_by)
    db.add(run)
    db.commit()

    try:
        # ── Stage 1: Ingestion ────────────────────────────────────────────────
        if user.platform == "spotify":
            ingested = ingest_spotify(db, user.id, run.id)
        else:
            ingested = ingest_apple_music(db, user.id, run.id)

        run.raw_tracks_ingested = ingested
        db.commit()

        # ── Stage 1b: Enrich Apple Music tracks ───────────────────────────────
        enriched = 0
        if user.platform == "apple_music":
            spotify_user = _find_user_by_platform(db, "spotify")
            if spotify_user:
                enriched = enrich_apple_tracks_with_spotify_features(
                    db, spotify_user.id, run.id
                )

        # ── Stage 2+3: Normalize + Match ──────────────────────────────────────
        raw_tracks = (
            db.query(RawTrack).filter(RawTrack.sync_run_id == run.id).all()
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

        from app.models.track_match import TrackMatch
        canonical_count = (
            db.query(TrackMatch.canonical_track_id)
            .join(RawTrack, TrackMatch.raw_track_id == RawTrack.id)
            .filter(RawTrack.sync_run_id == run.id)
            .distinct()
            .count()
        )

        run.raw_tracks_ingested = ingested
        run.matched_tracks = matched
        run.manual_review_count = manual_queue
        run.canonical_tracks_total = canonical_count
        db.commit()

        # ── Stage 4: Taste Scoring ────────────────────────────────────────────
        compute_taste_scores(db, user)

        # ── Stage 5+6+7: Candidate Pool → Compose → Publish ──────────────────
        # Requires both users to have taste scores
        user_a = _find_user_by_platform(db, "spotify")
        user_b = _find_user_by_platform(db, "apple_music")

        publish_results: dict = {}
        if user_a and user_b:
            candidates = build_candidate_pool(db, user_a, user_b)

            if candidates:
                settings_a = _get_or_create_settings(db, user_a)
                settings_b = _get_or_create_settings(db, user_b)

                # Use current user's settings for playlist size / ratios
                active_settings = settings_a if user.platform == "spotify" else settings_b
                entries = compose_playlist(candidates, active_settings)

                # Resolve platform IDs and build per-platform track lists
                spotify_ids: list[str] = []
                apple_ids: list[str] = []
                valid_entries = []

                for entry in entries:
                    canonical = db.get(CanonicalTrack, entry.canonical_track_id)
                    if not canonical:
                        continue

                    sp_id = resolve_spotify_id(db, canonical, user_a.id)
                    ap_id = resolve_apple_catalog_id(db, canonical, user_b.id)

                    if sp_id and ap_id:
                        spotify_ids.append(sp_id)
                        apple_ids.append(ap_id)
                        valid_entries.append((entry, sp_id, ap_id))

                # Publish to Spotify
                try:
                    sp_playlist_id = publish_to_spotify(db, user_a.id, spotify_ids, settings_a)
                    _save_playlist_record(db, run.id, "spotify", sp_playlist_id,
                                          settings_a.target_playlist_name, valid_entries, "a")
                    publish_results["spotify"] = "published"
                except Exception as e:
                    publish_results["spotify_error"] = str(e)

                # Publish to Apple Music
                try:
                    ap_playlist_id = publish_to_apple_music(db, user_b.id, apple_ids, settings_b)
                    _save_playlist_record(db, run.id, "apple_music", ap_playlist_id,
                                          settings_b.target_playlist_name, valid_entries, "b")
                    publish_results["apple_music"] = "published"
                except Exception as e:
                    publish_results["apple_music_error"] = str(e)

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.metrics = {
            "ingested": ingested,
            "enriched_with_spotify_features": enriched,
            "matched": matched,
            "manual_queue": manual_queue,
            "canonical_tracks": canonical_count,
            "playlist_tracks": len(spotify_ids) if "spotify_ids" in dir() else 0,
            **publish_results,
        }
        db.commit()

    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise

    return run


def _save_playlist_record(
    db: Session,
    sync_run_id: uuid.UUID,
    platform: str,
    platform_playlist_id: str,
    name: str,
    valid_entries: list,
    score_user: str,  # "a" or "b"
) -> None:
    from datetime import datetime, timezone
    playlist = Playlist(
        sync_run_id=sync_run_id,
        platform=platform,
        platform_playlist_id=platform_playlist_id,
        name=name,
        track_count=len(valid_entries),
        publish_status="published",
        published_at=datetime.now(timezone.utc),
    )
    db.add(playlist)
    db.flush()

    for i, (entry, sp_id, ap_id) in enumerate(valid_entries):
        platform_track_id = sp_id if platform == "spotify" else ap_id
        db.add(PlaylistTrack(
            playlist_id=playlist.id,
            canonical_track_id=entry.canonical_track_id,
            platform_track_id=platform_track_id,
            bucket=entry.bucket,
            position=i,
            score_a=entry.score_a,
            score_b=entry.score_b,
        ))
    db.commit()
