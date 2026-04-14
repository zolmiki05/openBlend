import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.pkce_state import PKCEState
from app.models.platform_token import PlatformToken
from app.utils.crypto import decrypt, encrypt

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

SPOTIFY_SCOPES = " ".join([
    "user-top-read",
    "user-read-recently-played",
    "user-library-read",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
])


def _generate_pkce_pair() -> tuple[str, str]:
    """Returns (code_verifier, code_challenge)."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def create_authorization_url(db: Session, user_id) -> str:
    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(16)

    pkce = PKCEState(
        user_id=user_id,
        state=state,
        code_verifier=code_verifier,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(pkce)
    db.commit()

    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "state": state,
        "scope": SPOTIFY_SCOPES,
    }
    return f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(db: Session, code: str, state: str) -> dict | None:
    pkce = (
        db.query(PKCEState)
        .filter(
            PKCEState.state == state,
            PKCEState.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if not pkce:
        return None

    user_id = pkce.user_id
    code_verifier = pkce.code_verifier
    db.delete(pkce)
    db.commit()

    with httpx.Client() as client:
        response = client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
                "client_id": settings.spotify_client_id,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        return None

    token_data = response.json()
    _upsert_platform_token(db, user_id, token_data)
    return {"user_id": str(user_id)}


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
        "expires_in": 3600,   # Web Player tokens typically live ~1 hr
        "scope": "",
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
    token.scope = token_data.get("scope")
    db.commit()
    return token
