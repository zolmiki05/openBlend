"""
Taste profile scoring.

For each user–canonical_track pair, compute a signal score based on:
  - max source weight across all raw tracks for this pair
  - recency of the most recent sighting (exponential decay, 30-day half-life)
  - frequency (count of distinct source appearances)
  - whether the track was explicitly saved
  - how many playlists it appears in
"""

import math
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.canonical_track import CanonicalTrack
from app.models.raw_track import RawTrack
from app.models.taste_score import TasteScore
from app.models.track_match import TrackMatch
from app.models.user import User

RECENCY_HALF_LIFE_DAYS = 30.0
FREQUENCY_BONUS_PER_SOURCE = 0.05
MAX_FREQUENCY_BONUS = 0.30
SAVE_BONUS = 0.20
PLAYLIST_BONUS_PER_ENTRY = 0.05
MAX_PLAYLIST_BONUS = 0.15
# Last.fm: loved tracks receive the same bonus as saved songs
SAVED_SOURCES = {"saved_songs", "lastfm_loved"}
PLAYLIST_SOURCES = {"playlist", "library_playlist"}
# Last.fm: play count bonus (50 plays = full bonus, capped at 0.25)
LASTFM_PLAYCOUNT_SCALE = 50
LASTFM_PLAYCOUNT_MAX_BONUS = 0.25


def _compute_score(raw_tracks: list[RawTrack]) -> tuple[float, dict]:
    now = datetime.now(timezone.utc)

    max_weight = max(rt.source_weight for rt in raw_tracks)

    most_recent = max(rt.ingested_at for rt in raw_tracks)
    if most_recent.tzinfo is None:
        most_recent = most_recent.replace(tzinfo=timezone.utc)
    days_ago = max((now - most_recent).total_seconds() / 86400, 0)
    recency_factor = math.exp(-days_ago / RECENCY_HALF_LIFE_DAYS)

    frequency = len(raw_tracks)
    frequency_bonus = min((frequency - 1) * FREQUENCY_BONUS_PER_SOURCE, MAX_FREQUENCY_BONUS)

    is_saved = any(rt.source_type in SAVED_SOURCES for rt in raw_tracks)
    save_bonus = SAVE_BONUS if is_saved else 0.0

    playlist_count = sum(1 for rt in raw_tracks if rt.source_type in PLAYLIST_SOURCES)
    playlist_bonus = min(playlist_count * PLAYLIST_BONUS_PER_ENTRY, MAX_PLAYLIST_BONUS)

    # Last.fm play-count bonus: derived from top-tracks entries that carry a play_count
    lastfm_top = [rt for rt in raw_tracks if rt.source_type.startswith("lastfm_top")]
    if lastfm_top:
        max_playcount = max(
            (rt.raw_data or {}).get("play_count", 0) for rt in lastfm_top
        )
        lastfm_playcount_bonus = (
            min(max_playcount / LASTFM_PLAYCOUNT_SCALE, 1.0) * LASTFM_PLAYCOUNT_MAX_BONUS
        )
    else:
        lastfm_playcount_bonus = 0.0

    score = (
        max_weight * recency_factor
        + frequency_bonus
        + save_bonus
        + playlist_bonus
        + lastfm_playcount_bonus
    )

    return score, {
        "max_source_weight": max_weight,
        "frequency": frequency,
        "is_saved": is_saved,
        "playlist_count": playlist_count,
        "lastfm_playcount_bonus": lastfm_playcount_bonus,
    }


def compute_taste_scores(db: Session, user: User) -> int:
    """
    Compute or refresh taste scores for all canonical tracks this user has raw data for.
    Upserts into taste_scores table.
    Returns the number of scores written.
    """
    # Get all canonical tracks this user has raw tracks for, grouped
    rows = (
        db.query(TrackMatch.canonical_track_id, RawTrack)
        .join(RawTrack, TrackMatch.raw_track_id == RawTrack.id)
        .filter(RawTrack.user_id == user.id)
        .all()
    )

    # Group raw tracks by canonical_track_id
    grouped: dict[uuid.UUID, list[RawTrack]] = {}
    for canonical_id, raw in rows:
        grouped.setdefault(canonical_id, []).append(raw)

    count = 0
    for canonical_id, raw_tracks in grouped.items():
        score, breakdown = _compute_score(raw_tracks)

        existing = (
            db.query(TasteScore)
            .filter(
                TasteScore.user_id == user.id,
                TasteScore.canonical_track_id == canonical_id,
            )
            .first()
        )
        if existing:
            existing.score = score
            existing.max_source_weight = breakdown["max_source_weight"]
            existing.frequency = breakdown["frequency"]
            existing.is_saved = breakdown["is_saved"]
            existing.playlist_count = breakdown["playlist_count"]
            existing.lastfm_playcount_bonus = breakdown["lastfm_playcount_bonus"]
            existing.computed_at = datetime.now(timezone.utc)
        else:
            db.add(TasteScore(
                user_id=user.id,
                canonical_track_id=canonical_id,
                score=score,
                max_source_weight=breakdown["max_source_weight"],
                frequency=breakdown["frequency"],
                is_saved=breakdown["is_saved"],
                playlist_count=breakdown["playlist_count"],
                lastfm_playcount_bonus=breakdown["lastfm_playcount_bonus"],
            ))
        count += 1

    db.commit()
    return count
