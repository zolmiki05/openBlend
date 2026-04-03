from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_password_changed
from app.models.user import User
from app.schemas.user import PlatformConnectionStatus
from app.services.apple_music import generate_developer_token, store_user_token

router = APIRouter(prefix="/auth/apple-music", tags=["apple_music"])


class DeveloperTokenResponse(BaseModel):
    developer_token: str


class UserTokenRequest(BaseModel):
    music_user_token: str


@router.get("/developer-token", response_model=DeveloperTokenResponse)
def get_developer_token(current_user: User = Depends(require_password_changed)):
    if current_user.platform != "apple_music":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not configured for Apple Music",
        )
    token = generate_developer_token()
    return DeveloperTokenResponse(developer_token=token)


@router.post("/user-token")
def store_music_user_token(
    body: UserTokenRequest,
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    if current_user.platform != "apple_music":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not configured for Apple Music",
        )
    store_user_token(db, current_user.id, body.music_user_token)
    return {"message": "Apple Music connected successfully"}


@router.get("/status", response_model=PlatformConnectionStatus)
def apple_music_status(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    from app.models.platform_token import PlatformToken

    token = (
        db.query(PlatformToken)
        .filter(
            PlatformToken.user_id == current_user.id,
            PlatformToken.platform == "apple_music",
        )
        .first()
    )
    return PlatformConnectionStatus(
        platform="apple_music",
        connected=token is not None,
        token_expiry=token.token_expiry if token else None,
    )
