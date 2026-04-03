"""
Spotify playlist publisher — diff-based.

Reads the current playlist contents, calculates the delta, and applies only
add/remove operations. Reorder is skipped in MVP.
"""

import time
import uuid

import httpx
from sqlalchemy.orm import Session

from app.models.platform_token import PlatformToken
from app.models.user_settings import UserSettings
from app.services.spotify import refresh_spotify_token
from app.utils.crypto import decrypt

SPOTIFY_API = "https://api.spotify.com/v1"


def _get_token(db: Session, user_id: uuid.UUID) -> str | None:
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


def _api(method: str, url: str, access_token: str, **kwargs) -> dict | None:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    for _ in range(3):
        resp = getattr(httpx, method)(url, headers=headers, timeout=20, **kwargs)
        if resp.status_code in (200, 201, 204):
            return resp.json() if resp.content else {}
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "5")))
            continue
        raise RuntimeError(f"Spotify API error {resp.status_code}: {resp.text}")
    return None


def _get_spotify_user_id(access_token: str) -> str:
    data = _api("get", f"{SPOTIFY_API}/me", access_token)
    return data["id"]


def _get_current_track_ids(playlist_id: str, access_token: str) -> list[str]:
    track_ids = []
    url = f"{SPOTIFY_API}/playlists/{playlist_id}/tracks"
    params: dict = {"fields": "items(track(id)),next", "limit": 100}
    while url:
        data = _api("get", url, access_token, params=params)
        if not data:
            break
        for item in data.get("items", []):
            track = item.get("track")
            if track and track.get("id"):
                track_ids.append(track["id"])
        url = data.get("next")
        params = {}
    return track_ids


def _create_playlist(user_id: str, name: str, access_token: str) -> str:
    data = _api(
        "post",
        f"{SPOTIFY_API}/users/{user_id}/playlists",
        access_token,
        json={"name": name, "public": False, "description": "Shared playlist by OpenBlend"},
    )
    return data["id"]


def publish_to_spotify(
    db: Session,
    spotify_user_id: uuid.UUID,
    track_ids: list[str],  # Spotify track IDs in final order
    settings: UserSettings,
) -> str:
    """
    Publish the playlist to Spotify using diff-based updates.
    Returns the Spotify playlist ID.
    """
    access_token = _get_token(db, spotify_user_id)
    if not access_token:
        raise RuntimeError("No valid Spotify token")

    sp_user_id = _get_spotify_user_id(access_token)

    # Create playlist if it doesn't exist yet
    if not settings.target_playlist_id:
        playlist_id = _create_playlist(sp_user_id, settings.target_playlist_name, access_token)
        settings.target_playlist_id = playlist_id
        db.commit()
    else:
        playlist_id = settings.target_playlist_id

    # Diff
    current_ids = _get_current_track_ids(playlist_id, access_token)
    current_set = set(current_ids)
    target_set = set(track_ids)

    to_remove = list(current_set - target_set)
    to_add = [tid for tid in track_ids if tid not in current_set]

    # Remove tracks
    for i in range(0, len(to_remove), 100):
        batch = to_remove[i:i + 100]
        _api(
            "delete",
            f"{SPOTIFY_API}/playlists/{playlist_id}/tracks",
            access_token,
            json={"tracks": [{"uri": f"spotify:track:{tid}"} for tid in batch]},
        )

    # Add tracks
    for i in range(0, len(to_add), 100):
        batch = to_add[i:i + 100]
        _api(
            "post",
            f"{SPOTIFY_API}/playlists/{playlist_id}/tracks",
            access_token,
            json={"uris": [f"spotify:track:{tid}" for tid in batch]},
        )

    return playlist_id
