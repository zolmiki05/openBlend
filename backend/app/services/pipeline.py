"""
Pipeline orchestrator.

Phase 2: Ingestion → Enrichment → Normalization → Matching
Phase 3: Taste Scoring → Candidate Pool
Phase 4: LLM Ranking → Platform Validation → Repair Loop → Publish
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
from app.services.llm_ranking import RankedTrack, rank_candidates
from app.services.matching import process_raw_track
from app.services.platform_validation import validate_tracks
from app.services.publisher.apple_music import publish_to_apple_music
from app.services.publisher.resolver import resolve_apple_catalog_id, resolve_spotify_id
from app.services.publisher.spotify import publish_to_spotify
from app.services.repair_loop import run_repair_loop
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


def _compute_target_counts(settings: UserSettings) -> dict[str, int]:
    # ratios are stored as integers out of 100 (e.g. 30 = 30%)
    size = settings.playlist_size
    return {
        "common": round(size * settings.ratio_common / 100),
        "bridge_a_to_b": round(size * settings.ratio_bridge_a_to_b / 100),
        "bridge_b_to_a": round(size * settings.ratio_bridge_b_to_a / 100),
        "experimental": round(size * settings.ratio_experimental / 100),
    }


def _resolve_and_validate(
    db: Session,
    ranked: list[RankedTrack],
    user_a_id: uuid.UUID,
    user_b_id: uuid.UUID,
    already_resolved: dict[uuid.UUID, tuple[str, str]],
    valid_ids: set[uuid.UUID],
    invalid_ids: set[uuid.UUID],
) -> None:
    """
    For each RankedTrack not yet in valid_ids or invalid_ids, resolve platform IDs
    and validate in batch. Mutates already_resolved, valid_ids, invalid_ids in place.
    """
    to_validate: list[tuple[uuid.UUID, str, str]] = []

    for rt in ranked:
        cid = rt.canonical_track_id
        if cid in valid_ids or cid in invalid_ids:
            continue
        if cid in already_resolved:
            to_validate.append((cid, *already_resolved[cid]))
            continue
        canonical = db.get(CanonicalTrack, cid)
        if not canonical:
            invalid_ids.add(cid)
            continue
        sp_id = resolve_spotify_id(db, canonical, user_a_id)
        ap_id = resolve_apple_catalog_id(db, canonical, user_b_id)
        if not sp_id or not ap_id:
            invalid_ids.add(cid)
            continue
        already_resolved[cid] = (sp_id, ap_id)
        to_validate.append((cid, sp_id, ap_id))

    if not to_validate:
        return

    statuses = validate_tracks(
        db,
        user_a_id,
        user_b_id,
        [(sp_id, ap_id) for _, sp_id, ap_id in to_validate],
    )
    for (cid, _sp, _ap), status in zip(to_validate, statuses):
        if status == "valid_both":
            valid_ids.add(cid)
        else:
            invalid_ids.add(cid)


def run_ingestion_pipeline(
    db: Session,
    user: User,
    triggered_by: str = "manual",
) -> SyncRun:
    """
    Full pipeline for one user:
      1.  Ingest platform data
      1b. Enrich Apple Music tracks with Spotify audio features
      2.  Normalize + match raw tracks
      4.  Taste scoring
      5.  Build candidate pool (requires both users to have scores)
      6.  LLM ranking
      7.  Platform validation
      8.  Repair loop (fill gaps, up to max_repair_loops)
      9.  Publish to both platforms

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

        # ── Stages 5–9: Both users required ──────────────────────────────────
        user_a = _find_user_by_platform(db, "spotify")
        user_b = _find_user_by_platform(db, "apple_music")

        publish_results: dict = {}
        final_track_count = 0

        if user_a and user_b:
            # ── Stage 5: Candidate Pool ───────────────────────────────────────
            candidates = build_candidate_pool(db, user_a, user_b)

            if candidates:
                settings_a = _get_or_create_settings(db, user_a)
                settings_b = _get_or_create_settings(db, user_b)
                active_settings = settings_a if user.platform == "spotify" else settings_b

                target_counts = _compute_target_counts(active_settings)

                # ── Stage 6: LLM Ranking ──────────────────────────────────────
                initial_ranked = rank_candidates(
                    db=db,
                    candidates=candidates,
                    target_counts=target_counts,
                    user_a_id=user_a.id,
                    user_b_id=user_b.id,
                    sync_run_id=run.id,
                    stage="ranking",
                )

                # Build explanation map (all ranks contribute)
                explanation_map: dict[uuid.UUID, str] = {
                    rt.canonical_track_id: rt.explanation for rt in initial_ranked
                }

                # ── Stage 7: Platform Validation (initial ranked set) ─────────
                resolved: dict[uuid.UUID, tuple[str, str]] = {}
                valid_ids: set[uuid.UUID] = set()
                invalid_ids: set[uuid.UUID] = set()

                _resolve_and_validate(
                    db, initial_ranked,
                    user_a.id, user_b.id,
                    resolved, valid_ids, invalid_ids,
                )

                # ── Stage 8: Repair Loop ──────────────────────────────────────
                repair_result = run_repair_loop(
                    db=db,
                    candidates=candidates,
                    initial_ranked=initial_ranked,
                    valid_ids=valid_ids,
                    invalid_ids=invalid_ids,
                    target_counts=target_counts,
                    user_a_id=user_a.id,
                    user_b_id=user_b.id,
                    max_loops=active_settings.max_repair_loops,
                    sync_run_id=run.id,
                )

                # Validate any new tracks added by the repair loop
                all_ranked = repair_result.ranked_tracks
                for rt in all_ranked:
                    explanation_map.setdefault(rt.canonical_track_id, rt.explanation)

                new_tracks = [
                    rt for rt in all_ranked
                    if rt.canonical_track_id not in valid_ids
                    and rt.canonical_track_id not in invalid_ids
                ]
                if new_tracks:
                    _resolve_and_validate(
                        db, new_tracks,
                        user_a.id, user_b.id,
                        resolved, valid_ids, invalid_ids,
                    )

                # ── Stage 9: Build final playlist, deduplicate, trim ──────────
                seen: set[uuid.UUID] = set()
                final_entries: list[tuple[RankedTrack, str, str]] = []

                for rt in all_ranked:
                    cid = rt.canonical_track_id
                    if cid in valid_ids and cid not in seen:
                        seen.add(cid)
                        sp_id, ap_id = resolved[cid]
                        final_entries.append((rt, sp_id, ap_id))

                total_target = sum(target_counts.values())
                final_entries = final_entries[:total_target]
                final_track_count = len(final_entries)

                spotify_ids = [sp_id for _, sp_id, _ in final_entries]
                apple_ids = [ap_id for _, _, ap_id in final_entries]

                # Publish to Spotify
                try:
                    sp_playlist_id = publish_to_spotify(
                        db, user_a.id, spotify_ids, settings_a
                    )
                    _save_playlist_record(
                        db, run.id, "spotify", sp_playlist_id,
                        settings_a.target_playlist_name,
                        final_entries, explanation_map, valid_ids,
                    )
                    publish_results["spotify"] = "published"
                except Exception as e:
                    publish_results["spotify_error"] = str(e)

                # Publish to Apple Music
                try:
                    ap_playlist_id = publish_to_apple_music(
                        db, user_b.id, apple_ids, settings_b
                    )
                    _save_playlist_record(
                        db, run.id, "apple_music", ap_playlist_id,
                        settings_b.target_playlist_name,
                        final_entries, explanation_map, valid_ids,
                    )
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
            "playlist_tracks": final_track_count,
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
    final_entries: list[tuple[RankedTrack, str, str]],
    explanation_map: dict[uuid.UUID, str],
    valid_ids: set[uuid.UUID],
) -> None:
    playlist = Playlist(
        sync_run_id=sync_run_id,
        platform=platform,
        platform_playlist_id=platform_playlist_id,
        name=name,
        track_count=len(final_entries),
        publish_status="published",
        published_at=datetime.now(timezone.utc),
    )
    db.add(playlist)
    db.flush()

    for i, (rt, sp_id, ap_id) in enumerate(final_entries):
        platform_track_id = sp_id if platform == "spotify" else ap_id
        db.add(PlaylistTrack(
            playlist_id=playlist.id,
            canonical_track_id=rt.canonical_track_id,
            platform_track_id=platform_track_id,
            bucket=rt.bucket,
            position=i,
            score_a=rt.score_a,
            score_b=rt.score_b,
            llm_explanation=explanation_map.get(rt.canonical_track_id, ""),
            validation_status="valid_both" if rt.canonical_track_id in valid_ids else "unknown",
        ))
    db.commit()
