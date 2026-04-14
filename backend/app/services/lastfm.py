"""
Last.fm integration service.

Handles:
  - OAuth flow: generate auth URL, exchange token for session key
  - Scrobbling: submit track plays to Last.fm
  - Data fetch: recent tracks, top tracks, loved tracks
"""

import hashlib
from typing import Any

import httpx

from app.config import settings

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
LASTFM_AUTH_URL = "https://www.last.fm/api/auth/"


def _sign(params: dict[str, str]) -> str:
    """MD5 signature required by Last.fm write API calls."""
    sig_str = "".join(
        f"{k}{v}" for k, v in sorted(params.items()) if k != "format"
    )
    sig_str += settings.lastfm_shared_secret
    return hashlib.md5(sig_str.encode("utf-8")).hexdigest()


def get_auth_url(callback_url: str) -> str:
    """Return the Last.fm authorization URL to redirect the user to."""
    return f"{LASTFM_AUTH_URL}?api_key={settings.lastfm_api_key}&cb={callback_url}"


def exchange_token(token: str) -> dict[str, str]:
    """
    Exchange a Last.fm auth token for a persistent session key.
    Returns {"session_key": ..., "username": ...}.
    Raises ValueError if Last.fm returns an error.
    """
    params: dict[str, str] = {
        "method": "auth.getSession",
        "api_key": settings.lastfm_api_key,
        "token": token,
    }
    params["api_sig"] = _sign(params)
    params["format"] = "json"

    resp = httpx.post(LASTFM_API, data=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise ValueError(f"Last.fm error {data['error']}: {data.get('message', 'unknown')}")

    session = data["session"]
    return {"session_key": session["key"], "username": session["name"]}


def get_recent_tracks(username: str, limit: int = 200) -> list[dict]:
    """Fetch recently played tracks for a user (excludes now-playing entry)."""
    params = {
        "method": "user.getRecentTracks",
        "user": username,
        "api_key": settings.lastfm_api_key,
        "limit": str(limit),
        "extended": "0",
        "format": "json",
    }
    try:
        resp = httpx.get(LASTFM_API, params=params, timeout=30)
        if resp.status_code != 200:
            return []
        tracks = resp.json().get("recenttracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        return [t for t in tracks if not t.get("@attr", {}).get("nowplaying")]
    except Exception:
        return []


def get_top_tracks(
    username: str, period: str = "1month", limit: int = 100
) -> list[dict]:
    """
    Fetch top tracks for a user.
    period: overall | 7day | 1month | 3month | 6month | 12month
    """
    params = {
        "method": "user.getTopTracks",
        "user": username,
        "period": period,
        "api_key": settings.lastfm_api_key,
        "limit": str(limit),
        "format": "json",
    }
    try:
        resp = httpx.get(LASTFM_API, params=params, timeout=30)
        if resp.status_code != 200:
            return []
        return resp.json().get("toptracks", {}).get("track", []) or []
    except Exception:
        return []


def get_loved_tracks(username: str, limit: int = 200) -> list[dict]:
    """Fetch loved (hearted) tracks for a user."""
    params = {
        "method": "user.getLovedTracks",
        "user": username,
        "api_key": settings.lastfm_api_key,
        "limit": str(limit),
        "format": "json",
    }
    try:
        resp = httpx.get(LASTFM_API, params=params, timeout=30)
        if resp.status_code != 200:
            return []
        tracks = resp.json().get("lovedtracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        return tracks or []
    except Exception:
        return []


def scrobble_tracks(
    session_key: str, tracks: list[dict[str, Any]]
) -> int:
    """
    Submit plays to Last.fm in batches of 50.
    Each track dict: {"artist": str, "title": str, "album": str|None, "timestamp": int}
    Returns count of accepted scrobbles.
    """
    if not tracks:
        return 0

    accepted = 0
    for i in range(0, len(tracks), 50):
        batch = tracks[i : i + 50]
        params: dict[str, str] = {
            "method": "track.scrobble",
            "api_key": settings.lastfm_api_key,
            "sk": session_key,
        }
        for j, t in enumerate(batch):
            params[f"artist[{j}]"] = t["artist"]
            params[f"track[{j}]"] = t["title"]
            params[f"timestamp[{j}]"] = str(t["timestamp"])
            if t.get("album"):
                params[f"album[{j}]"] = t["album"]

        params["api_sig"] = _sign(params)
        params["format"] = "json"

        try:
            resp = httpx.post(LASTFM_API, data=params, timeout=30)
            data = resp.json()
            attr = data.get("scrobbles", {}).get("@attr", {})
            accepted += int(attr.get("accepted", 0))
        except Exception:
            pass  # Best-effort — never fail the pipeline

    return accepted
