"""
Apple Music playlist publisher — full rebuild (MVP acceptable per spec).

Creates a library playlist if one doesn't exist, then clears and repopulates it.
Uses catalog song IDs (not library song IDs) when adding tracks.
"""

import time
import uuid

import httpx
from sqlalchemy.orm import Session

from app.models.platform_token import PlatformToken
from app.models.user_settings import UserSettings
from app.services.apple_music import generate_developer_token
from app.utils.crypto import decrypt

APPLE_API = "https://api.music.apple.com/v1"


def _get_tokens(db: Session, user_id: uuid.UUID) -> tuple[str, str] | None:
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == user_id, PlatformToken.platform == "apple_music")
        .first()
    )
    if not token:
        return None
    return generate_developer_token(), decrypt(token.access_token_encrypted)


def _headers(developer_token: str, music_user_token: str) -> dict:
    return {
        "Authorization": f"Bearer {developer_token}",
        "Music-User-Token": music_user_token,
        "Content-Type": "application/json",
    }


def _api(method: str, url: str, dev_token: str, music_token: str, **kwargs) -> dict | None:
    hdrs = _headers(dev_token, music_token)
    for _ in range(3):
        resp = getattr(httpx, method)(url, headers=hdrs, timeout=20, **kwargs)
        if resp.status_code in (200, 201, 204):
            return resp.json() if resp.content else {}
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "5")))
            continue
        raise RuntimeError(f"Apple Music API error {resp.status_code}: {resp.text}")
    return None


def _create_playlist(name: str, dev_token: str, music_token: str) -> str:
    data = _api(
        "post",
        f"{APPLE_API}/me/library/playlists",
        dev_token,
        music_token,
        json={"attributes": {"name": name, "description": "Shared playlist by OpenBlend"}},
    )
    return data["data"][0]["id"]


def _clear_playlist(playlist_id: str, dev_token: str, music_token: str) -> None:
    """Remove all tracks from a library playlist."""
    url = f"{APPLE_API}/me/library/playlists/{playlist_id}/tracks"
    data = _api("get", url, dev_token, music_token)
    if not data or not data.get("data"):
        return
    track_ids = [item["id"] for item in data["data"]]
    if track_ids:
        _api(
            "delete",
            url,
            dev_token,
            music_token,
            json={"data": [{"id": tid, "type": "library-songs"} for tid in track_ids]},
        )


def publish_to_apple_music(
    db: Session,
    apple_user_id: uuid.UUID,
    catalog_track_ids: list[str],  # Apple Music catalog song IDs
    settings: UserSettings,
) -> str:
    """
    Publish the playlist to Apple Music (full rebuild).
    Returns the Apple Music library playlist ID.
    """
    tokens = _get_tokens(db, apple_user_id)
    if not tokens:
        raise RuntimeError("No valid Apple Music token")

    dev_token, music_token = tokens

    if not settings.target_playlist_id:
        playlist_id = _create_playlist(settings.target_playlist_name, dev_token, music_token)
        settings.target_playlist_id = playlist_id
        db.commit()
    else:
        playlist_id = settings.target_playlist_id
        _clear_playlist(playlist_id, dev_token, music_token)

    # Add tracks in batches of 100
    for i in range(0, len(catalog_track_ids), 100):
        batch = catalog_track_ids[i:i + 100]
        _api(
            "post",
            f"{APPLE_API}/me/library/playlists/{playlist_id}/tracks",
            dev_token,
            music_token,
            json={"data": [{"id": tid, "type": "songs"} for tid in batch]},
        )

    return playlist_id
