import uuid
from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    is_temp_password: bool
    platform: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PlatformConnectionStatus(BaseModel):
    platform: str
    connected: bool
    token_expiry: datetime | None = None
