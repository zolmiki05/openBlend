from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_password_changed
from app.models.user import User
from app.models.user_settings import UserSettings

router = APIRouter(prefix="/settings", tags=["settings"])

ScheduleType = Literal["daily", "every_two_days", "weekly", "manual"]


class SettingsOut(BaseModel):
    target_playlist_name: str
    sync_schedule: str
    playlist_size: int
    allow_explicit: bool
    ratio_common: int
    ratio_bridge_a_to_b: int
    ratio_bridge_b_to_a: int
    ratio_experimental: int
    max_repair_loops: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingsIn(BaseModel):
    target_playlist_name: str | None = Field(None, min_length=1, max_length=256)
    sync_schedule: ScheduleType | None = None
    playlist_size: int | None = Field(None, ge=10, le=100)
    allow_explicit: bool | None = None
    ratio_common: int | None = Field(None, ge=0, le=100)
    ratio_bridge_a_to_b: int | None = Field(None, ge=0, le=100)
    ratio_bridge_b_to_a: int | None = Field(None, ge=0, le=100)
    ratio_experimental: int | None = Field(None, ge=0, le=100)
    max_repair_loops: int | None = Field(None, ge=0, le=10)

    @model_validator(mode="after")
    def ratios_sum_to_100(self) -> "SettingsIn":
        ratios = [self.ratio_common, self.ratio_bridge_a_to_b,
                  self.ratio_bridge_b_to_a, self.ratio_experimental]
        provided = [r for r in ratios if r is not None]
        if len(provided) > 0 and len(provided) < 4:
            raise ValueError("All four ratio fields must be provided together")
        if len(provided) == 4 and sum(provided) != 100:
            raise ValueError("Ratios must sum to 100")
        return self


def _get_or_create(db: Session, user_id) -> UserSettings:
    s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not s:
        s = UserSettings(user_id=user_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.get("", response_model=SettingsOut)
def get_settings(
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    return _get_or_create(db, current_user.id)


@router.put("", response_model=SettingsOut)
def update_settings(
    body: SettingsIn,
    current_user: User = Depends(require_password_changed),
    db: Session = Depends(get_db),
):
    s = _get_or_create(db, current_user.id)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(s, field, value)

    db.commit()
    db.refresh(s)
    return s
