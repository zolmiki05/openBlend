import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_password_changed
from app.models.platform_token import PlatformToken
from app.models.user import User
from app.schemas.user import PlatformConnectionStatus
from app.services import lastfm as lfm_svc
from app.utils.crypto import decrypt, encrypt

router = APIRouter(prefix="/auth/lastfm", tags=["lastfm"])

_CALLBACK_PATH = "/auth/lastfm/callback"


class LastFmAuthUrlResponse(BaseModel):
    auth_url: str


class LastFmTokenRequest(BaseModel):
    token: str


class LastFmStatus(PlatformConnectionStatus):
    username: str | None = None


# ── Auth flow ─────────────────────────────────────────────────────────────────

@router.get("/auth-url", response_model=LastFmAuthUrlResponse)
def get_auth_url(current_user: User = Depends(require_password_changed)):
    if current_user.platform != "apple_music":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Last.fm integration is for Apple Music users",
        )
    if not settings.lastfm_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Last.fm API key not configured",
        )
    callback_url = f"{settings.frontend_url}{_CALLBACK_PATH}"
    return LastFmAuthUrlResponse(auth_url=lfm_svc.get_auth_url(callback_url))


@router.post("/callback")
def lastfm_callback(
    body: LastFmTokenRequest,
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    """Exchange the Last.fm auth token for a session key and persist it."""
    if current_user.platform != "apple_music":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Last.fm integration is for Apple Music users",
        )
    try:
        result = lfm_svc.exchange_token(body.token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    token = (
        db.query(PlatformToken)
        .filter(PlatformToken.user_id == current_user.id, PlatformToken.platform == "lastfm")
        .first()
    )
    if not token:
        token = PlatformToken(user_id=current_user.id, platform="lastfm")
        db.add(token)

    token.access_token_encrypted = encrypt(result["session_key"])
    token.scope = result["username"]  # Reuse scope field to store username
    db.commit()

    return {"message": "Last.fm connected successfully", "username": result["username"]}


# ── Status / disconnect ────────────────────────────────────────────────────────

@router.get("/status", response_model=LastFmStatus)
def lastfm_status(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    token = (
        db.query(PlatformToken)
        .filter(
            PlatformToken.user_id == current_user.id,
            PlatformToken.platform == "lastfm",
        )
        .first()
    )
    if not token:
        return LastFmStatus(platform="lastfm", connected=False)

    # Quick liveness check
    connected = False
    try:
        resp = httpx.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "user.getInfo",
                "user": token.scope,
                "api_key": settings.lastfm_api_key,
                "format": "json",
            },
            timeout=8,
        )
        connected = resp.status_code == 200 and "error" not in resp.json()
    except Exception:
        pass

    return LastFmStatus(platform="lastfm", connected=connected, username=token.scope)


@router.delete("/disconnect")
def lastfm_disconnect(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    token = (
        db.query(PlatformToken)
        .filter(
            PlatformToken.user_id == current_user.id,
            PlatformToken.platform == "lastfm",
        )
        .first()
    )
    if token:
        db.delete(token)
        db.commit()
    return {"message": "Last.fm disconnected"}


# ── Manual scrobble trigger ────────────────────────────────────────────────────

@router.post("/scrobble")
def trigger_scrobble(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    """Manually push unscrobbled Apple Music plays to Last.fm."""
    if current_user.platform != "apple_music":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scrobbling is only available for Apple Music users",
        )
    from app.services.ingestion.lastfm import scrobble_apple_music_plays

    count = scrobble_apple_music_plays(db, current_user.id)
    return {"scrobbled": count}
