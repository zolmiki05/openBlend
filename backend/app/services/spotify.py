import base64
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.platform_token import PlatformToken
from app.utils.crypto import decrypt, encrypt

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


def store_paste_token(db: Session, user_id, access_token: str) -> dict | None:
    """
    Validate a manually-pasted Spotify access token by calling /v1/me.
    If valid, store it (without a refresh token — expires in ~1 hr).
    Returns the user profile dict on success, None on failure.
    """
    with httpx.Client() as client:
        resp = client.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    if resp.status_code != 200:
        return None

    profile = resp.json()
    token_data = {
        "access_token": access_token,
        "expires_in": 3600,
    }
    _upsert_platform_token(db, user_id, token_data)
    return {"display_name": profile.get("display_name") or profile.get("id")}


def refresh_spotify_token(db: Session, platform_token: PlatformToken) -> bool:
    if not platform_token.refresh_token_encrypted:
        return False

    refresh_token = decrypt(platform_token.refresh_token_encrypted)

    with httpx.Client() as client:
        credentials = base64.b64encode(
            f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
        ).decode()
        response = client.post(
            SPOTIFY_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    if response.status_code != 200:
        return False

    token_data = response.json()
    platform_token.access_token_encrypted = encrypt(token_data["access_token"])
    if "refresh_token" in token_data:
        platform_token.refresh_token_encrypted = encrypt(token_data["refresh_token"])
    expires_in = token_data.get("expires_in", 3600)
    platform_token.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    db.commit()
    return True


def _upsert_platform_token(db: Session, user_id, token_data: dict) -> PlatformToken:
    expires_in = token_data.get("expires_in", 3600)
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == user_id, PlatformToken.platform == "spotify")
        .first()
    )
    if not token:
        token = PlatformToken(user_id=user_id, platform="spotify")
        db.add(token)

    token.access_token_encrypted = encrypt(token_data["access_token"])
    if token_data.get("refresh_token"):
        token.refresh_token_encrypted = encrypt(token_data["refresh_token"])
    token.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    token.scope = token_data.get("scope", "")
    db.commit()
    return token
