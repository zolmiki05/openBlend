"""
Platform validation (Stage 7).

For each LLM-selected track, verifies that it is available on both Spotify
and Apple Music. Only "valid_both" tracks proceed to the final playlist.
"""

import time
import uuid

import httpx
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.models.platform_token import PlatformToken
from app.services.apple_music import generate_developer_token
from app.services.spotify import refresh_spotify_token
from app.utils.crypto import decrypt

SPOTIFY_API = "https://api.spotify.com/v1"
APPLE_API = "https://api.music.apple.com/v1"


def _spotify_token(db: Session, user_id: uuid.UUID) -> str | None:
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


def _apple_tokens(db: Session, user_id: uuid.UUID) -> tuple[str, str] | None:
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == user_id, PlatformToken.platform == "apple_music")
        .first()
    )
    if not token:
        return None
    return generate_developer_token(), decrypt(token.access_token_encrypted)


def _get(url: str, headers: dict, params: dict | None = None) -> int:
    """Return HTTP status code."""
    for _ in range(2):
        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", "3")))
                continue
            return resp.status_code
        except Exception:
            return 0
    return 0


def validate_tracks(
    db: Session,
    spotify_user_id: uuid.UUID,
    apple_user_id: uuid.UUID,
    track_pairs: list[tuple[str, str]],  # [(spotify_id, apple_catalog_id), ...]
) -> list[str]:
    """
    Validate each (spotify_id, apple_catalog_id) pair.
    Returns a list of statuses, one per track:
      "valid_both" | "valid_spotify_only" | "valid_apple_only" | "not_found"
    """
    sp_token = _spotify_token(db, spotify_user_id)
    ap_tokens = _apple_tokens(db, apple_user_id)

    statuses: list[str] = []
    storefront = app_settings.apple_music_storefront

    for sp_id, ap_id in track_pairs:
        sp_ok = False
        ap_ok = False

        if sp_token and sp_id:
            code = _get(
                f"{SPOTIFY_API}/tracks/{sp_id}",
                {"Authorization": f"Bearer {sp_token}"},
            )
            sp_ok = code == 200

        if ap_tokens and ap_id:
            dev_token, music_token = ap_tokens
            code = _get(
                f"{APPLE_API}/catalog/{storefront}/songs/{ap_id}",
                {"Authorization": f"Bearer {dev_token}", "Music-User-Token": music_token},
            )
            ap_ok = code == 200

        if sp_ok and ap_ok:
            statuses.append("valid_both")
        elif sp_ok:
            statuses.append("valid_spotify_only")
        elif ap_ok:
            statuses.append("valid_apple_only")
        else:
            statuses.append("not_found")

    return statuses
