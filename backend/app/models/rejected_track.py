import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RejectedTrack(Base):
    """Tracks permanently excluded from candidate pools (user rejections or validation failures)."""

    __tablename__ = "rejected_tracks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rejected_by: Mapped[str] = mapped_column(String(32), nullable=False)  # user_a | user_b | validation | manual
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
