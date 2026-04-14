from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user, require_password_changed
from app.models.user import User
from app.schemas.user import PlatformConnectionStatus
from app.services.spotify import (
    create_authorization_url,
    exchange_code_for_tokens,
    store_paste_token,
)

router = APIRouter(prefix="/auth/spotify", tags=["spotify"])


@router.get("/authorize")
def spotify_authorize(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    if current_user.platform != "spotify":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not configured for Spotify",
        )
    auth_url = create_authorization_url(db, current_user.id)
    return {"authorization_url": auth_url}


class ExchangeRequest(BaseModel):
    code: str
    state: str


@router.post("/exchange")
def spotify_exchange(
    body: ExchangeRequest,
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    """Exchange authorization code for tokens (called by the frontend callback page)."""
    result = exchange_code_for_tokens(db, body.code, body.state)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token exchange failed — code may have expired or state is invalid",
        )
    return {"connected": True}


@router.get("/callback")
def spotify_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Legacy server-side callback — kept for backward compatibility."""
    if error:
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?spotify_error={error}"
        )

    result = exchange_code_for_tokens(db, code, state)
    if not result:
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?spotify_error=token_exchange_failed"
        )

    return RedirectResponse(url=f"{settings.frontend_url}/settings?spotify_connected=true")


class PasteTokenRequest(BaseModel):
    access_token: str


@router.post("/paste-token")
def spotify_paste_token(
    body: PasteTokenRequest,
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    """
    Accept a Spotify access token pasted manually by the user
    (e.g. copied from open.spotify.com/get_access_token).
    Validates the token against the Spotify API before storing it.
    """
    if current_user.platform != "spotify":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not configured for Spotify",
        )
    result = store_paste_token(db, current_user.id, body.access_token)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Spotify token. Please copy a fresh one.",
        )
    return {"connected": True, "display_name": result.get("display_name")}


@router.get("/status", response_model=PlatformConnectionStatus)
def spotify_status(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    from app.models.platform_token import PlatformToken

    token = (
        db.query(PlatformToken)
        .filter(
            PlatformToken.user_id == current_user.id,
            PlatformToken.platform == "spotify",
        )
        .first()
    )
    return PlatformConnectionStatus(
        platform="spotify",
        connected=token is not None,
        token_expiry=token.token_expiry if token else None,
    )
