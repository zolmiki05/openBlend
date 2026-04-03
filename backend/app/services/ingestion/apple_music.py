"""
Apple Music ingestion service.
Pulls library playlists and recently played tracks.
Note: Apple Music library songs do not expose audio features — audio_features is stored as null.
"""

import time
import uuid
from typing import Generator

import httpx
from sqlalchemy.orm import Session

from app.models.platform_token import PlatformToken
from app.models.raw_track import SOURCE_WEIGHTS, RawTrack
from app.services.apple_music import generate_developer_token
from app.utils.crypto import decrypt

APPLE_API = "https://api.music.apple.com/v1"
MAX_RETRIES = 3


def _get_tokens(db: Session, user_id: uuid.UUID) -> tuple[str, str] | None:
    """Returns (developer_token, music_user_token) or None."""
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == user_id, PlatformToken.platform == "apple_music")
        .first()
    )
    if not token:
        return None
    developer_token = generate_developer_token()
    music_user_token = decrypt(token.access_token_encrypted)
    return developer_token, music_user_token


def _get(
    url: str,
    developer_token: str,
    music_user_token: str,
    params: dict | None = None,
) -> dict | None:
    headers = {
        "Authorization": f"Bearer {developer_token}",
        "Music-User-Token": music_user_token,
    }
    for attempt in range(MAX_RETRIES):
        resp = httpx.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            time.sleep(retry_after)
            continue
        return None
    return None


def _paginate(
    url: str,
    developer_token: str,
    music_user_token: str,
) -> Generator[dict, None, None]:
    next_url: str | None = url
    while next_url:
        data = _get(next_url, developer_token, music_user_token)
        if not data:
            break
        for item in data.get("data", []):
            yield item
        next_url = data.get("next")
        if next_url and not next_url.startswith("http"):
            next_url = f"https://api.music.apple.com{next_url}"


def _extract_library_song(item: dict) -> dict | None:
    attrs = item.get("attributes", {})
    title = attrs.get("name")
    artist = attrs.get("artistName", "")
    if not title:
        return None
    return {
        "platform_id": item["id"],
        "isrc": None,  # Library songs typically lack ISRC
        "title": title,
        "artists": [a.strip() for a in artist.split(",") if a.strip()],
        "album": attrs.get("albumName"),
        "duration_ms": attrs.get("durationInMillis"),
        "raw_data": item,
    }


def _save_raw_tracks(
    db: Session,
    tracks: list[dict],
    user_id: uuid.UUID,
    sync_run_id: uuid.UUID | None,
    source_type: str,
) -> int:
    count = 0
    for t in tracks:
        existing = (
            db.query(RawTrack)
            .filter(
                RawTrack.user_id == user_id,
                RawTrack.platform_id == t["platform_id"],
                RawTrack.platform == "apple_music",
                RawTrack.sync_run_id == sync_run_id,
            )
            .first()
        )
        if existing:
            continue

        raw = RawTrack(
            user_id=user_id,
            sync_run_id=sync_run_id,
            platform="apple_music",
            source_type=source_type,
            source_weight=SOURCE_WEIGHTS[source_type],
            platform_id=t["platform_id"],
            isrc=t.get("isrc"),
            title=t["title"],
            artists=t["artists"],
            album=t.get("album"),
            duration_ms=t.get("duration_ms"),
            audio_features=None,  # Not available for Apple Music
            raw_data=t["raw_data"],
        )
        db.add(raw)
        count += 1
    db.commit()
    return count


def ingest_apple_music(
    db: Session,
    user_id: uuid.UUID,
    sync_run_id: uuid.UUID | None = None,
) -> int:
    """Ingest Apple Music sources for a user. Returns total raw tracks saved."""
    tokens = _get_tokens(db, user_id)
    if not tokens:
        raise RuntimeError("No valid Apple Music token for user")

    developer_token, music_user_token = tokens
    total = 0

    # Library playlists → their tracks
    playlists_url = f"{APPLE_API}/me/library/playlists"
    playlist_tracks: list[dict] = []
    for playlist in _paginate(playlists_url, developer_token, music_user_token):
        playlist_id = playlist["id"]
        tracks_url = f"{APPLE_API}/me/library/playlists/{playlist_id}/tracks"
        for track in _paginate(tracks_url, developer_token, music_user_token):
            fields = _extract_library_song(track)
            if fields:
                playlist_tracks.append(fields)

    total += _save_raw_tracks(
        db, playlist_tracks, user_id, sync_run_id, "library_playlist"
    )

    # Recently played
    recent_url = f"{APPLE_API}/me/recent/played"
    recent_tracks: list[dict] = []
    data = _get(
        recent_url,
        developer_token,
        music_user_token,
        {"types": "library-songs", "limit": "25"},
    )
    if data:
        for item in data.get("data", []):
            fields = _extract_library_song(item)
            if fields:
                recent_tracks.append(fields)

    total += _save_raw_tracks(
        db, recent_tracks, user_id, sync_run_id, "apple_recently_played"
    )

    return total
