"""
Spotify ingestion service.
Pulls top tracks, saved songs, recently played, and bound playlist.
Fetches audio features for each track (used later for taste overlap scoring).
Handles pagination and 429 rate-limit backoff.
"""

import time
import uuid
from typing import Generator

import httpx
from sqlalchemy.orm import Session

from app.models.platform_token import PlatformToken
from app.models.raw_track import SOURCE_WEIGHTS, RawTrack
from app.services.spotify import refresh_spotify_token
from app.utils.crypto import decrypt

SPOTIFY_API = "https://api.spotify.com/v1"
MAX_RETRIES = 3


def _get_access_token(db: Session, user_id: uuid.UUID) -> str | None:
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == user_id, PlatformToken.platform == "spotify")
        .first()
    )
    if not token:
        return None

    from datetime import datetime, timezone
    if token.token_expiry and token.token_expiry < datetime.now(timezone.utc):
        if not refresh_spotify_token(db, token):
            return None

    return decrypt(token.access_token_encrypted)


def _get(url: str, access_token: str, params: dict | None = None) -> dict | None:
    headers = {"Authorization": f"Bearer {access_token}"}
    for attempt in range(MAX_RETRIES):
        resp = httpx.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            time.sleep(retry_after)
            continue
        if resp.status_code == 401:
            return None
        return None
    return None


def _paginate(url: str, access_token: str, limit: int = 50) -> Generator[dict, None, None]:
    """Yield individual track objects from a paginated Spotify endpoint."""
    params: dict = {"limit": limit}
    while url:
        data = _get(url, access_token, params)
        if not data:
            break
        items = data.get("items", [])
        for item in items:
            if item:
                yield item
        url = data.get("next")
        params = {}  # subsequent requests use the full next URL


def _extract_track_fields(track_obj: dict) -> dict | None:
    """Extract normalised fields from a Spotify track object."""
    if not track_obj or track_obj.get("type") != "track":
        return None
    artists = [a["name"] for a in track_obj.get("artists", [])]
    isrc = track_obj.get("external_ids", {}).get("isrc")
    return {
        "platform_id": track_obj["id"],
        "isrc": isrc,
        "title": track_obj["name"],
        "artists": artists,
        "album": track_obj.get("album", {}).get("name"),
        "duration_ms": track_obj.get("duration_ms"),
        "raw_data": track_obj,
    }


def _fetch_audio_features(track_ids: list[str], access_token: str) -> dict[str, dict]:
    """Fetch audio features for up to 100 tracks at a time."""
    result: dict[str, dict] = {}
    for i in range(0, len(track_ids), 100):
        batch = track_ids[i:i + 100]
        data = _get(
            f"{SPOTIFY_API}/audio-features",
            access_token,
            {"ids": ",".join(batch)},
        )
        if data:
            for feat in data.get("audio_features", []):
                if feat:
                    result[feat["id"]] = {
                        "tempo": feat.get("tempo"),
                        "energy": feat.get("energy"),
                        "valence": feat.get("valence"),
                        "danceability": feat.get("danceability"),
                        "acousticness": feat.get("acousticness"),
                        "instrumentalness": feat.get("instrumentalness"),
                        "loudness": feat.get("loudness"),
                        "speechiness": feat.get("speechiness"),
                        "key": feat.get("key"),
                        "mode": feat.get("mode"),
                        "time_signature": feat.get("time_signature"),
                    }
    return result


def _save_raw_tracks(
    db: Session,
    tracks: list[dict],
    user_id: uuid.UUID,
    sync_run_id: uuid.UUID | None,
    source_type: str,
    audio_features: dict[str, dict],
) -> int:
    count = 0
    for t in tracks:
        existing = (
            db.query(RawTrack)
            .filter(
                RawTrack.user_id == user_id,
                RawTrack.platform_id == t["platform_id"],
                RawTrack.platform == "spotify",
                RawTrack.sync_run_id == sync_run_id,
            )
            .first()
        )
        if existing:
            continue

        raw = RawTrack(
            user_id=user_id,
            sync_run_id=sync_run_id,
            platform="spotify",
            source_type=source_type,
            source_weight=SOURCE_WEIGHTS[source_type],
            platform_id=t["platform_id"],
            isrc=t["isrc"],
            title=t["title"],
            artists=t["artists"],
            album=t["album"],
            duration_ms=t["duration_ms"],
            audio_features=audio_features.get(t["platform_id"]),
            raw_data=t["raw_data"],
        )
        db.add(raw)
        count += 1
    db.commit()
    return count


def ingest_spotify(
    db: Session,
    user_id: uuid.UUID,
    sync_run_id: uuid.UUID | None = None,
) -> int:
    """Ingest all Spotify sources for a user. Returns total raw tracks saved."""
    access_token = _get_access_token(db, user_id)
    if not access_token:
        raise RuntimeError("No valid Spotify access token for user")

    all_tracks: dict[str, list[dict]] = {
        "top_tracks_short": [],
        "top_tracks_medium": [],
        "top_tracks_long": [],
        "recently_played": [],
        "saved_songs": [],
    }

    # Top tracks
    for term, source_type in [
        ("short_term", "top_tracks_short"),
        ("medium_term", "top_tracks_medium"),
        ("long_term", "top_tracks_long"),
    ]:
        url = f"{SPOTIFY_API}/me/top/tracks"
        for item in _paginate(url, access_token):
            fields = _extract_track_fields(item)
            if fields:
                all_tracks[source_type].append(fields)

    # Recently played
    data = _get(
        f"{SPOTIFY_API}/me/player/recently-played",
        access_token,
        {"limit": 50},
    )
    if data:
        for item in data.get("items", []):
            track_obj = item.get("track", {})
            fields = _extract_track_fields(track_obj)
            if fields:
                all_tracks["recently_played"].append(fields)

    # Saved songs
    for item in _paginate(f"{SPOTIFY_API}/me/tracks", access_token):
        track_obj = item.get("track", {}) if isinstance(item, dict) else {}
        fields = _extract_track_fields(track_obj)
        if fields:
            all_tracks["saved_songs"].append(fields)

    # Collect all unique track IDs for audio features batch fetch
    all_ids = list({t["platform_id"] for tracks in all_tracks.values() for t in tracks})
    audio_features = _fetch_audio_features(all_ids, access_token)

    total = 0
    for source_type, tracks in all_tracks.items():
        total += _save_raw_tracks(db, tracks, user_id, sync_run_id, source_type, audio_features)

    return total
