"""
Platform ID resolver.

For each canonical track, resolves the platform-specific track ID needed
to add it to a Spotify or Apple Music playlist.

Spotify:  uses the raw_track.platform_id directly (it's the Spotify track ID)
Apple Music: needs the catalog song ID (not the library song ID stored in raw_track).
             Resolves via ISRC search first, then title+artist catalog search.
"""

import time
import uuid

import httpx
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.canonical_track import CanonicalTrack
from app.models.platform_token import PlatformToken
from app.models.raw_track import RawTrack
from app.models.track_match import TrackMatch
from app.services.apple_music import generate_developer_token
from app.services.normalization import normalize_text
from app.services.spotify import refresh_spotify_token
from app.utils.crypto import decrypt

SPOTIFY_API = "https://api.spotify.com/v1"
APPLE_API = "https://api.music.apple.com/v1"
SEARCH_THRESHOLD = 80.0


def _spotify_token(db: Session, spotify_user_id: uuid.UUID) -> str | None:
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == spotify_user_id, PlatformToken.platform == "spotify")
        .first()
    )
    if not token:
        return None
    from datetime import datetime, timezone
    if token.token_expiry and token.token_expiry < datetime.now(timezone.utc):
        if not refresh_spotify_token(db, token):
            return None
    return decrypt(token.access_token_encrypted)


def _apple_tokens(db: Session, apple_user_id: uuid.UUID) -> tuple[str, str] | None:
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == apple_user_id, PlatformToken.platform == "apple_music")
        .first()
    )
    if not token:
        return None
    return generate_developer_token(), decrypt(token.access_token_encrypted)


def _get(url: str, headers: dict, params: dict | None = None) -> dict | None:
    for _ in range(3):
        resp = httpx.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "5")))
            continue
        break
    return None


def resolve_spotify_id(
    db: Session,
    canonical: CanonicalTrack,
    spotify_user_id: uuid.UUID,
) -> str | None:
    """Get the Spotify track ID for a canonical track."""
    # Try via existing raw track match
    match = (
        db.query(TrackMatch)
        .join(RawTrack, TrackMatch.raw_track_id == RawTrack.id)
        .filter(
            TrackMatch.canonical_track_id == canonical.id,
            RawTrack.platform == "spotify",
        )
        .first()
    )
    if match:
        raw = db.get(RawTrack, match.raw_track_id)
        if raw:
            return raw.platform_id

    # Fallback: catalog search
    access_token = _spotify_token(db, spotify_user_id)
    if not access_token:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    query = f"track:{canonical.display_title} artist:{canonical.display_artists[0] if canonical.display_artists else ''}"
    data = _get(f"{SPOTIFY_API}/search", headers, {"q": query, "type": "track", "limit": 5})
    if not data:
        return None

    norm_title = canonical.normalized_title
    norm_artists = ",".join(canonical.normalized_artists)

    for item in data.get("tracks", {}).get("items", []):
        t_score = fuzz.token_sort_ratio(norm_title, normalize_text(item["name"]))
        a_score = fuzz.token_sort_ratio(
            norm_artists,
            normalize_text(",".join(a["name"] for a in item["artists"])),
        )
        if t_score >= SEARCH_THRESHOLD and a_score >= SEARCH_THRESHOLD:
            return item["id"]
    return None


def resolve_apple_catalog_id(
    db: Session,
    canonical: CanonicalTrack,
    apple_user_id: uuid.UUID,
    storefront: str = "us",
) -> str | None:
    """Get the Apple Music catalog song ID for a canonical track."""
    tokens = _apple_tokens(db, apple_user_id)
    if not tokens:
        return None

    developer_token, music_user_token = tokens
    headers = {
        "Authorization": f"Bearer {developer_token}",
        "Music-User-Token": music_user_token,
    }

    # ISRC lookup first
    if canonical.isrc:
        data = _get(
            f"{APPLE_API}/catalog/{storefront}/songs",
            headers,
            {"filter[isrc]": canonical.isrc},
        )
        if data and data.get("data"):
            return data["data"][0]["id"]

    # Title + artist catalog search
    query = f"{canonical.display_title} {canonical.display_artists[0] if canonical.display_artists else ''}"
    data = _get(
        f"{APPLE_API}/catalog/{storefront}/search",
        headers,
        {"term": query, "types": "songs", "limit": "10"},
    )
    if not data:
        return None

    norm_title = canonical.normalized_title
    norm_artists = ",".join(canonical.normalized_artists)

    for item in data.get("results", {}).get("songs", {}).get("data", []):
        attrs = item.get("attributes", {})
        t_score = fuzz.token_sort_ratio(norm_title, normalize_text(attrs.get("name", "")))
        a_score = fuzz.token_sort_ratio(norm_artists, normalize_text(attrs.get("artistName", "")))
        if t_score >= SEARCH_THRESHOLD and a_score >= SEARCH_THRESHOLD:
            return item["id"]
    return None
