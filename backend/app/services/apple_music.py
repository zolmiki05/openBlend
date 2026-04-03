import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models.platform_token import PlatformToken
from app.utils.crypto import encrypt

APPLE_MUSIC_TOKEN_EXPIRY_SECONDS = 15777000  # ~6 months (Apple's maximum)


def generate_developer_token() -> str:
    """
    Generate an Apple Music developer token (JWT signed with the private key
    from Apple Developer Portal). This token is sent to the frontend so that
    MusicKit JS can initialize and authenticate the user.
    """
    private_key = settings.apple_music_private_key.replace("\\n", "\n")

    now = int(time.time())
    payload = {
        "iss": settings.apple_music_team_id,
        "iat": now,
        "exp": now + APPLE_MUSIC_TOKEN_EXPIRY_SECONDS,
    }
    headers = {"alg": "ES256", "kid": settings.apple_music_key_id}

    return pyjwt.encode(payload, private_key, algorithm="ES256", headers=headers)


def store_user_token(db: Session, user_id, music_user_token: str) -> PlatformToken:
    """Store the music user token received from MusicKit JS in the frontend."""
    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == user_id, PlatformToken.platform == "apple_music")
        .first()
    )
    if not token:
        token = PlatformToken(user_id=user_id, platform="apple_music")
        db.add(token)

    token.access_token_encrypted = encrypt(music_user_token)
    # Apple Music user tokens are short-lived (~6 hours); store approximate expiry
    token.token_expiry = datetime.now(timezone.utc) + timedelta(hours=6)
    db.commit()
    return token
