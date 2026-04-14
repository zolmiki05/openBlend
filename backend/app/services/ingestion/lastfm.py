"""
Last.fm ingestion service.

Two responsibilities:
  1. ingest_lastfm()       — pull Last.fm listening history as raw_tracks so the taste
                             scoring pipeline can incorporate Last.fm signals alongside
                             Apple Music data.
  2. scrobble_apple_music_plays() — take Apple Music recently-played raw tracks and
                             scrobble any not yet recorded to Last.fm.

Last.fm source types ingested as raw_tracks:
  lastfm_loved       — loved/hearted tracks  (treated as "saved" in scoring)
  lastfm_top_short   — top tracks, 1-month window
  lastfm_top_medium  — top tracks, 6-month window
  lastfm_top_long    — top tracks, all-time
  lastfm_recent      — recently played tracks
"""

import uuid

from sqlalchemy.orm import Session

from app.models.lastfm_scrobble import LastFmScrobble
from app.models.platform_token import PlatformToken
from app.models.raw_track import SOURCE_WEIGHTS, RawTrack
from app.services import lastfm as lfm_svc
from app.utils.crypto import decrypt


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_lastfm_creds(db: Session, user_id: uuid.UUID) -> tuple[str, str] | None:
    """Returns (session_key, username) or None if not connected."""
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == user_id, PlatformToken.platform == "lastfm")
        .first()
    )
    if not token or not token.scope:
        return None
    return decrypt(token.access_token_encrypted), token.scope


def _save_raw_tracks(
    db: Session,
    tracks: list[dict],
    user_id: uuid.UUID,
    sync_run_id: uuid.UUID | None,
    source_type: str,
) -> int:
    count = 0
    for t in tracks:
        platform_id = t.get("platform_id", "")
        if not platform_id:
            continue
        existing = (
            db.query(RawTrack)
            .filter(
                RawTrack.user_id == user_id,
                RawTrack.platform == "lastfm",
                RawTrack.platform_id == platform_id,
                RawTrack.source_type == source_type,
                RawTrack.sync_run_id == sync_run_id,
            )
            .first()
        )
        if existing:
            continue
        db.add(RawTrack(
            user_id=user_id,
            sync_run_id=sync_run_id,
            platform="lastfm",
            source_type=source_type,
            source_weight=SOURCE_WEIGHTS[source_type],
            platform_id=platform_id,
            isrc=None,
            title=t["title"],
            artists=t["artists"],
            album=t.get("album"),
            duration_ms=None,
            audio_features=None,
            raw_data=t["raw_data"],
        ))
        count += 1
    db.commit()
    return count


def _parse_top_track(item: dict) -> dict | None:
    title = item.get("name", "").strip()
    artist = item.get("artist", {}).get("name", "").strip()
    if not title or not artist:
        return None
    mbid = item.get("mbid") or ""
    play_count = int(item.get("playcount", 0))
    rank = int(item.get("@attr", {}).get("rank", 0))
    key = f"{artist.lower()}::{title.lower()}::{mbid}"
    return {
        "platform_id": f"lastfm:top:{key}",
        "title": title,
        "artists": [artist],
        "album": None,
        "raw_data": {"mbid": mbid, "play_count": play_count, "rank": rank},
    }


def _parse_loved_track(item: dict) -> dict | None:
    title = item.get("name", "").strip()
    artist = item.get("artist", {}).get("name", "").strip()
    if not title or not artist:
        return None
    mbid = item.get("mbid") or ""
    key = f"{artist.lower()}::{title.lower()}::{mbid}"
    return {
        "platform_id": f"lastfm:loved:{key}",
        "title": title,
        "artists": [artist],
        "album": None,
        "raw_data": {"mbid": mbid, "loved": True},
    }


def _parse_recent_track(item: dict) -> dict | None:
    title = item.get("name", "").strip()
    artist = item.get("artist", {}).get("#text", "").strip()
    if not title or not artist:
        return None
    mbid = item.get("mbid") or ""
    uts = item.get("date", {}).get("uts", "")
    key = f"{artist.lower()}::{title.lower()}::{uts}"
    return {
        "platform_id": f"lastfm:recent:{key}",
        "title": title,
        "artists": [artist],
        "album": item.get("album", {}).get("#text") or None,
        "raw_data": {"mbid": mbid, "played_at_uts": uts},
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def ingest_lastfm(
    db: Session,
    user_id: uuid.UUID,
    sync_run_id: uuid.UUID | None = None,
) -> int:
    """
    Ingest Last.fm listening history for an Apple Music user.
    Silently returns 0 if the user has no Last.fm connection.
    """
    creds = _get_lastfm_creds(db, user_id)
    if not creds:
        return 0

    _session_key, username = creds
    total = 0

    # Loved tracks
    loved_raw = [_parse_loved_track(t) for t in lfm_svc.get_loved_tracks(username)]
    total += _save_raw_tracks(
        db, [t for t in loved_raw if t], user_id, sync_run_id, "lastfm_loved"
    )

    # Top tracks — three time windows
    for source_type, period in [
        ("lastfm_top_short", "1month"),
        ("lastfm_top_medium", "6month"),
        ("lastfm_top_long", "overall"),
    ]:
        tops_raw = [_parse_top_track(t) for t in lfm_svc.get_top_tracks(username, period=period)]
        total += _save_raw_tracks(
            db, [t for t in tops_raw if t], user_id, sync_run_id, source_type
        )

    # Recent tracks
    recent_raw = [_parse_recent_track(t) for t in lfm_svc.get_recent_tracks(username)]
    total += _save_raw_tracks(
        db, [t for t in recent_raw if t], user_id, sync_run_id, "lastfm_recent"
    )

    return total


def scrobble_apple_music_plays(db: Session, user_id: uuid.UUID) -> int:
    """
    Find Apple Music recently-played raw tracks not yet scrobbled and
    submit them to Last.fm. Returns count of newly scrobbled tracks.
    """
    creds = _get_lastfm_creds(db, user_id)
    if not creds:
        return 0

    session_key, _username = creds

    # Raw tracks already scrobbled
    already_scrobbled_ids = {
        row.raw_track_id
        for row in db.query(LastFmScrobble.raw_track_id)
        .filter(LastFmScrobble.user_id == user_id)
        .all()
    }

    unscrobbled = (
        db.query(RawTrack)
        .filter(
            RawTrack.user_id == user_id,
            RawTrack.platform == "apple_music",
            RawTrack.source_type == "apple_recently_played",
            ~RawTrack.id.in_(already_scrobbled_ids) if already_scrobbled_ids else True,
        )
        .all()
    )

    if not unscrobbled:
        return 0

    batch = [
        {
            "artist": rt.artists[0] if rt.artists else "Unknown",
            "title": rt.title,
            "album": rt.album,
            "timestamp": int(rt.ingested_at.timestamp()),
        }
        for rt in unscrobbled
    ]

    lfm_svc.scrobble_tracks(session_key, batch)

    for rt in unscrobbled:
        db.add(LastFmScrobble(user_id=user_id, raw_track_id=rt.id))
    db.commit()

    return len(unscrobbled)
