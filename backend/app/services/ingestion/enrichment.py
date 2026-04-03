"""
Cross-platform enrichment: enrich Apple Music raw tracks with Spotify audio features.

Strategy:
1. ISRC match — search Spotify catalog with the Apple Music track's ISRC (most reliable)
2. Title + artist search — fuzzy catalog search as fallback
3. Fetch audio features for the matched Spotify track ID
4. Update the Apple Music RawTrack.audio_features in-place

Uses the Spotify user's stored access token for all catalog API calls.
No personal Spotify data is accessed — catalog search works with any valid token.
"""

import time
import uuid
from urllib.parse import quote

import httpx
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.platform_token import PlatformToken
from app.models.raw_track import RawTrack
from app.services.normalization import normalize_text
from app.services.spotify import refresh_spotify_token
from app.utils.crypto import decrypt

SPOTIFY_API = "https://api.spotify.com/v1"
MAX_RETRIES = 3
ENRICHMENT_TITLE_THRESHOLD = 80.0
ENRICHMENT_ARTIST_THRESHOLD = 75.0


def _get_spotify_token(db: Session, spotify_user_id: uuid.UUID) -> str | None:
    token = (
        db.query(PlatformToken)
        .filter(
            PlatformToken.user_id == spotify_user_id,
            PlatformToken.platform == "spotify",
        )
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
    for _ in range(MAX_RETRIES):
        resp = httpx.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "5")))
            continue
        break
    return None


def _search_by_isrc(isrc: str, access_token: str) -> str | None:
    """Return Spotify track ID for a given ISRC, or None."""
    data = _get(
        f"{SPOTIFY_API}/search",
        access_token,
        {"q": f"isrc:{isrc}", "type": "track", "limit": 1},
    )
    if not data:
        return None
    items = data.get("tracks", {}).get("items", [])
    return items[0]["id"] if items else None


def _search_by_title_artist(
    title: str,
    artists: list[str],
    duration_ms: int | None,
    access_token: str,
) -> str | None:
    """Return Spotify track ID via title+artist search with similarity check."""
    artist_str = " ".join(artists[:2])  # use first 2 artists to avoid overly long query
    query = f"track:{quote(title)} artist:{quote(artist_str)}"
    data = _get(
        f"{SPOTIFY_API}/search",
        access_token,
        {"q": query, "type": "track", "limit": 10},
    )
    if not data:
        return None

    norm_title = normalize_text(title)
    norm_artists = normalize_text(",".join(artists))

    for item in data.get("tracks", {}).get("items", []):
        cand_title = normalize_text(item.get("name", ""))
        cand_artists = normalize_text(",".join(a["name"] for a in item.get("artists", [])))

        title_score = fuzz.token_sort_ratio(norm_title, cand_title)
        artist_score = fuzz.token_sort_ratio(norm_artists, cand_artists)

        if title_score < ENRICHMENT_TITLE_THRESHOLD or artist_score < ENRICHMENT_ARTIST_THRESHOLD:
            continue

        # Duration check when available
        if duration_ms and item.get("duration_ms"):
            if abs(duration_ms - item["duration_ms"]) > 5000:
                continue

        return item["id"]

    return None


def _fetch_audio_features(track_id: str, access_token: str) -> dict | None:
    data = _get(f"{SPOTIFY_API}/audio-features/{track_id}", access_token)
    if not data:
        return None
    return {
        "tempo": data.get("tempo"),
        "energy": data.get("energy"),
        "valence": data.get("valence"),
        "danceability": data.get("danceability"),
        "acousticness": data.get("acousticness"),
        "instrumentalness": data.get("instrumentalness"),
        "loudness": data.get("loudness"),
        "speechiness": data.get("speechiness"),
        "key": data.get("key"),
        "mode": data.get("mode"),
        "time_signature": data.get("time_signature"),
        "_enriched_from_spotify_id": track_id,
    }


def enrich_apple_tracks_with_spotify_features(
    db: Session,
    spotify_user_id: uuid.UUID,
    sync_run_id: uuid.UUID | None = None,
) -> int:
    """
    For each Apple Music raw track in the given run (or all unenriched if run_id is None),
    attempt to find a matching Spotify catalog track and copy its audio features.
    Returns the number of tracks successfully enriched.
    """
    access_token = _get_spotify_token(db, spotify_user_id)
    if not access_token:
        return 0

    query = db.query(RawTrack).filter(
        RawTrack.platform == "apple_music",
        RawTrack.audio_features.is_(None),
    )
    if sync_run_id:
        query = query.filter(RawTrack.sync_run_id == sync_run_id)

    apple_tracks = query.all()
    enriched = 0

    for track in apple_tracks:
        spotify_id: str | None = None

        # Try ISRC first
        if track.isrc:
            spotify_id = _search_by_isrc(track.isrc, access_token)

        # Fallback to title+artist search
        if not spotify_id:
            spotify_id = _search_by_title_artist(
                track.title,
                track.artists,
                track.duration_ms,
                access_token,
            )

        if not spotify_id:
            continue

        features = _fetch_audio_features(spotify_id, access_token)
        if features:
            track.audio_features = features
            enriched += 1

    if enriched:
        db.commit()

    return enriched
