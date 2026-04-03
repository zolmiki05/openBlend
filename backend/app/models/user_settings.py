import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Platform playlist ID where the shared playlist is published
    target_playlist_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_playlist_name: Mapped[str] = mapped_column(String(256), nullable=False, default="OpenBlend")
    # Sync schedule
    sync_schedule: Mapped[str] = mapped_column(
        String(32), nullable=False, default="weekly"
    )  # daily | every_two_days | weekly | manual
    # Playlist composition
    playlist_size: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    allow_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Bucket ratios (stored as integers out of 100)
    ratio_common: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    ratio_bridge_a_to_b: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    ratio_bridge_b_to_a: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    ratio_experimental: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_repair_loops: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
